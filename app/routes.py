# web-monitor/app/routes.py
import datetime
import json
from datetime import timezone
from collections import defaultdict
from flask import Blueprint, jsonify, render_template, current_app, flash, url_for, session, redirect, request
from flask_admin import AdminIndexView, BaseView, expose
from flask_admin.menu import MenuLink
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user, login_user, logout_user, login_required
from .extensions import db
from .models import HealthCheckLog, User, MonitoredSite
from .services import site_statuses, status_lock
from .forms import LoginForm, MonitoredSiteForm, ChangePasswordForm

# --- 【新增】时区转换和格式化帮助函数 ---
def to_gmt8(utc_dt):
    """将 UTC datetime 对象转换为 GMT+8 时区的 datetime 对象"""
    if utc_dt is None:
        return None
    # 创建一个 UTC+8 的时区对象
    gmt8_tz = timezone(datetime.timedelta(hours=8))
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(gmt8_tz)


def format_datetime_gmt8(view, context, model, name):
    """Flask-Admin 字段格式化函数，将 UTC 时间转为 GMT+8 字符串"""
    utc_dt = getattr(model, name)
    gmt8_dt = to_gmt8(utc_dt)
    return gmt8_dt.strftime('%Y-%m-%d %H:%M:%S') if gmt8_dt else ''


# --- 安全后台的核心 ---
# 创建一个自定义的后台主页视图，要求登录
class MyAdminIndexView(AdminIndexView):
    @expose('/')
    @login_required
    def index(self):
        return self.render('admin/index.html', username=current_user.username)
    @expose('/change-password', methods=['GET', 'POST'])
    def change_password(self):
        form = ChangePasswordForm()
        if form.validate_on_submit():
            if not current_user.check_password(form.current_password.data):
                flash('您当前的密码不正确，请重试。', 'danger')
                return redirect(url_for('.change_password'))

            current_user.set_password(form.new_password.data)
            db.session.commit()

            flash('您的密码已成功更新！', 'success')
            return redirect(url_for('.index'))

        return self.render('admin/change_password.html', form=form)
    @expose('/login', methods=['GET', 'POST'])
    def login(self):
        # 如果用户已经登录，直接带他们去后台主页，避免看到登录页
        if current_user.is_authenticated:
            return redirect(url_for('.index'))

        form = LoginForm()
        if form.validate_on_submit():
            user = User.query.filter_by(username=form.username.data).first()
            if user is None or not user.check_password(form.password.data):
                flash('无效的用户名或密码')
                # 这样即使用户名密码错误，也停留在登录页
                return redirect(url_for('.login'))
            login_user(user, remember=form.remember_me.data)

            # 登录成功后，跳转到后台主页
            return redirect(url_for('.index'))

        return self.render('admin/login.html', form=form)

    @expose('/logout')
    @login_required  # 最好也给 logout 加上保护
    def logout(self):
        logout_user()
        flash('您已成功退出登录。')
        # 退出后，跳转回登录页面
        return redirect(url_for('.login'))

    @expose('/set-theme/<theme_name>')
    @login_required
    def set_theme(self, theme_name):
        # 将用户选择的主题名字存入 session
        session['admin_theme'] = theme_name
        # 重定向回用户刚才所在的页面
        return redirect(request.referrer or url_for('.index'))

class ThemeSettingsView(BaseView):
    # a. 定义菜单图标
    menu_icon_type = 'fa'
    menu_icon_value = 'fa-paint-brush'

    @expose('/')
    def index(self):
        # 从 admin 实例获取可用主题列表
        available_themes = self.admin.available_themes or []
        # 渲染一个专门用于显示主题列表的模板
        return self.render('admin/set_theme.html', themes=available_themes)
    # 只有登录用户才能访问这个视图
    def is_accessible(self):
        return current_user.is_authenticated

# 创建一个安全的模型视图基类，所有需要登录才能访问的视图都应继承它
class SecureModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated

    def _handle_view(self, name, **kwargs):
        if not self.is_accessible():
            return redirect(url_for('admin.login', next=request.url))

# --- 路由蓝图 ---
main_bp = Blueprint('main', __name__)

# --- 自定义的后台管理视图 ---
class MonitoredSiteView(SecureModelView):
    menu_icon_type = 'fa'
    menu_icon_value = 'fa-globe'
    form = MonitoredSiteForm
    column_list = ['name', 'url', 'is_active']
    column_labels = {
        'name': '网站名称',
        'url': '监控地址',
        'is_active': '是否启用'
    }

    column_searchable_list = ['name', 'url']
    column_filters = ['is_active']
   # form_columns = ['name', 'url', 'is_active']
    page_size = 50

class HealthCheckLogView(SecureModelView):
    menu_icon_type = 'fa'
    menu_icon_value = 'fa-history'
    column_list = ['site_name', 'timestamp', 'status', 'response_time_seconds']
    column_labels = {
        'site_name': '网站名称',
        'timestamp': '检查时间',
        'status': '状态',
        'response_time_seconds': '响应时间(秒)'
    }
    column_searchable_list = ['site_name', 'status']
    column_filters = ['site_name', 'status', 'timestamp']
    can_create = False
    can_edit = False
    can_delete = True
    page_size = 50
    column_formatters = {
        'timestamp': format_datetime_gmt8
    }
    # 【可选但推荐】让后台日志按时间倒序排列，最新的在最前面
    column_default_sort = ('timestamp', True)

    # 只在认证后才显示的链接类
class AuthenticatedMenuLink(MenuLink):
    def is_accessible(self):
        return current_user.is_authenticated


# --- 前端面板和 API 路由 ---
@main_bp.route('/')
def dashboard():
    site_objects = MonitoredSite.query.filter_by(is_active=True).all()
    site_names = [site.name for site in site_objects]
    current_year = datetime.datetime.now().year
    with status_lock:
        # 使用 json.dumps 将 python 字典转换为 JSON 字符串
        initial_statuses_json = json.dumps(site_statuses)
    return render_template(
        'dashboard.html',
        sites=site_names,
        current_year=current_year,
        DATA_RETENTION_DAYS=current_app.config['DATA_RETENTION_DAYS'],
        initial_statuses_json=initial_statuses_json
    )
@main_bp.route('/health', methods=['GET'])
def get_health_status():
    with status_lock:
        return jsonify(site_statuses)

@main_bp.route('/api/history', methods=['GET'])
def get_history():
    """提供历史监控数据的 API (已升级为按时间分段聚合)"""
    selected_sites = request.args.getlist('sites')
    start_time_str = request.args.get('start_time')
    end_time_str = request.args.get('end_time')
    try:
        start_time_naive = datetime.datetime.fromisoformat(start_time_str)
        end_time_naive = datetime.datetime.fromisoformat(end_time_str)
        start_time_utc = start_time_naive.astimezone(timezone.utc)
        end_time_utc = end_time_naive.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return jsonify({"error": "无效的时间格式或参数缺失"}), 400
    results = {}
    NUM_INTERVALS = 90  # 将整个时间范围切分成90个分段
    EPSILON = 1e-9
    for site in selected_sites:
        # 1. 一次性查询所有范围内的日志
        logs = db.session.query(HealthCheckLog).filter(
            HealthCheckLog.site_name == site,
            HealthCheckLog.timestamp.between(start_time_utc, end_time_utc)
        ).order_by(HealthCheckLog.timestamp.asc()).all()
        # 2. 计算总体统计数据 (用于图表和右上角显示)
        up_count = sum(1 for log in logs if log.status in ['正常', '访问过慢'])
        availability = (up_count / len(logs) * 100) if logs else 0
        valid_times = [log.response_time_seconds for log in logs if log.response_time_seconds is not None]
        avg_response_time = sum(valid_times) / len(valid_times) if valid_times else 0
        # 3. 【核心逻辑】将日志分配到时间分段中
        total_duration = (end_time_utc - start_time_utc).total_seconds()
        interval_duration = total_duration / NUM_INTERVALS if total_duration > 0 else 0

        intervals = [defaultdict(list) for _ in range(NUM_INTERVALS)]

        for log in logs:
            log_timestamp_utc = log.timestamp.replace(tzinfo=timezone.utc)
            time_since_start = (log_timestamp_utc - start_time_utc).total_seconds()
            index = min(int((time_since_start / interval_duration) + EPSILON), NUM_INTERVALS - 1) if interval_duration > 0 else 0
            intervals[index]['logs'].append(log)
        # 4. 处理每个分段，生成最终给前端的数据
        uptime_intervals = []
        for i, interval_data in enumerate(intervals):
            interval_logs = interval_data['logs']
            start_interval_utc = start_time_utc + datetime.timedelta(seconds=i * interval_duration)
            end_interval_utc = start_interval_utc + datetime.timedelta(seconds=interval_duration)
            # 将UTC时间转回用户的本地时区以供显示
            local_tz = start_time_naive.tzinfo
            start_display = start_interval_utc.astimezone(local_tz).strftime('%H:%M')
            end_display = end_interval_utc.astimezone(local_tz).strftime('%H:%M, %m/%d')
            if not interval_logs:
                status = "nodata"
                details = "无数据"
            else:
                if any(log.status == '无法访问' for log in interval_logs):
                    status = "down"
                    # 提取该时段内的错误信息
                    down_log = next((log for log in interval_logs if log.status == '无法访问'), None)
                    details = "未知错误"
                    if down_log:
                        error_text = getattr(down_log, 'error_detail', '无详细信息')
                        details = f"错误: {error_text or '无详细信息'}"
                elif any(log.status == '访问过慢' for log in interval_logs):
                    status = "slow"
                    details = "响应过慢"
                else:
                    status = "up"
                    details = "一切正常"

            uptime_intervals.append({
                "time_range": f"{start_display} - {end_display}",
                "status": status,
                "details": details
            })
        # 5. 组装最终给前端的 JSON
        results[site] = {
            "overall_stats": {
                "avg_response_time": avg_response_time,
                "availability": availability
            },
            "uptime_intervals": uptime_intervals,
            # ECharts 折线图仍然需要原始的响应时间数据
            "response_times": {
                "timestamps": [to_gmt8(log.timestamp).strftime('%Y-%m-%d %H:%M') for log in logs],
                "times": [log.response_time_seconds for log in logs]
            }
        }

    return jsonify(results)
