# web-monitor/app/routes.py
import datetime
import json
from datetime import timezone
from flask import Blueprint, jsonify, render_template, current_app, flash, url_for, session, redirect, request
from flask_admin import AdminIndexView, BaseView, expose
from flask_admin.menu import MenuLink
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user, login_user, logout_user, login_required
from sqlalchemy import inspect as sa_inspect

from .extensions import db, scheduler
from .forms import (
    ChangePasswordForm,
    LoginForm,
    MonitoringSettingsForm,
    MonitoredSiteForm,
    PasswordResetForm,
)
from .models import (
    HealthCheckLog,
    MonitoringConfig,
    MonitoredSite,
    PasswordResetToken,
    User,
)
from .services import site_statuses, status_lock, send_management_notification

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


class NotificationSettingsView(BaseView):
    menu_icon_type = 'fa'
    menu_icon_value = 'fa-bell'

    @expose('/', methods=['GET', 'POST'])
    def index(self):
        if not current_user.is_authenticated:
            return redirect(url_for('admin.login', next=request.url))
        from .models import NotificationConfig
        from .forms import NotificationSettingsForm

        form = NotificationSettingsForm()
        config_record = NotificationConfig.get_or_create()
        if not form.is_submitted():
            config_record.populate_form(form)
        # 处理测试通知
        if form.test_webhook.data and form.validate():
            sample_payload = NotificationConfig.sample_payload()
            # 临时应用表单配置
            temp_config = {
                'GENERIC_WEBHOOK_ENABLED': form.webhook_enabled.data,
                'GENERIC_WEBHOOK_URL': form.webhook_url.data,
                'GENERIC_WEBHOOK_CONTENT_TYPE': form.webhook_content_type.data or 'application/json',
                'GENERIC_WEBHOOK_TEMPLATE': form.webhook_template.data
            }
            if form.webhook_headers.data:
                try:
                    import json
                    temp_config['GENERIC_WEBHOOK_HEADERS'] = json.loads(form.webhook_headers.data)
                except:
                    temp_config['GENERIC_WEBHOOK_HEADERS'] = {}
            else:
                temp_config['GENERIC_WEBHOOK_HEADERS'] = {}

            # 临时更新 app.config
            old_config = {}
            for key, value in temp_config.items():
                old_config[key] = current_app.config.get(key)
                current_app.config[key] = value

            # 发送测试
            from .services import send_generic_webhook
            success = send_generic_webhook('test_notification', sample_payload)

            # 恢复配置
            for key, value in old_config.items():
                current_app.config[key] = value

            if success:
                flash('测试通知发送成功！', 'success')
            else:
                flash('测试通知发送失败，请检查配置或查看日志。', 'danger')
            return redirect(url_for('.index'))
        # 保存配置
        if form.submit.data and form.validate_on_submit():
            try:
                config_record.update_from_form(form)
                db.session.commit()
                config_record.apply_to_config(current_app.config)

                operator = current_user.username if current_user.is_authenticated else None
                details = [
                    ('Webhook 状态', '已启用' if config_record.webhook_enabled else '已禁用'),
                    ('Webhook URL', config_record.webhook_url or '未配置')
                ]
                send_management_notification('通知配置更新', operator=operator, details=details)

                flash('通知配置已保存。', 'success')
                return redirect(url_for('.index'))
            except Exception as exc:
                db.session.rollback()
                current_app.logger.exception('保存通知配置失败: %s', exc)
                flash('保存配置失败，请稍后重试。', 'danger')
        elif form.is_submitted():
            flash('请修正表单中的错误后再提交。', 'danger')
        # 生成预览
        preview_payload = None
        preview_rendered = None
        preview_error = None

        if config_record.webhook_template:
            from .services import render_webhook_template
            preview_payload = NotificationConfig.sample_payload()
            preview_rendered, preview_error = render_webhook_template(
                config_record.webhook_template,
                preview_payload
            )
        return self.render(
            'admin/notification_settings.html',
            form=form,
            preview_rendered=preview_rendered,
            preview_error=preview_error,
            preview_payload=preview_payload,
            default_template=NotificationConfig.DEFAULT_TEMPLATE
        )

    def is_accessible(self):
        return current_user.is_authenticated

    def _handle_view(self, name, **kwargs):
        if not self.is_accessible():
            return redirect(url_for('admin.login', next=request.url))


# --- 安全后台的核心 ---
# 创建一个自定义的后台主页视图，要求登录
class MyAdminIndexView(AdminIndexView):
    @expose('/')
    @login_required
    def index(self):
        return self.render('admin/index.html', username=current_user.username)
    @expose('/change-password', methods=['GET', 'POST'])
    @login_required
    def change_password(self):
        form = ChangePasswordForm()
        if form.validate_on_submit():
            if not current_user.check_password(form.current_password.data):
                form.current_password.errors.append('当前密码不正确，请重试。')
                flash('请修正表单中的错误后再提交。', 'danger')
            elif form.new_password.data == form.current_password.data:
                form.new_password.errors.append('新密码不能与当前密码相同。')
                flash('请修正表单中的错误后再提交。', 'danger')
            else:
                try:
                    current_user.set_password(form.new_password.data)
                    db.session.commit()
                except Exception as exc:
                    db.session.rollback()
                    current_app.logger.exception('更新密码失败: %s', exc)
                    flash('保存新密码时出现错误，请稍后再试。', 'danger')
                else:
                    flash('您的密码已成功更新！', 'success')
                    return redirect(url_for('.index'))
        elif form.is_submitted():
            flash('请修正表单中的错误后再提交。', 'danger')

        return self.render('admin/change_password.html', form=form)
    @expose('/login', methods=['GET', 'POST'])
    def login(self):
        if current_user.is_authenticated:
            return redirect(url_for('.index'))

        form = LoginForm()
        if form.validate_on_submit():
            user = User.query.filter_by(username=form.username.data).first()
            if user is None or not user.check_password(form.password.data):
                flash('无效的用户名或密码。', 'danger')
            else:
                login_user(user, remember=form.remember_me.data)
                flash('登录成功，欢迎回来！', 'success')
                return redirect(url_for('.index'))
        elif form.is_submitted():
            flash('请填写用户名和密码。', 'danger')

        return self.render('admin/login.html', form=form)

    @expose('/forgot-password', methods=['GET', 'POST'])
    def forgot_password(self):
        if current_user.is_authenticated:
            return redirect(url_for('.index'))

        form = PasswordResetForm()
        if form.validate_on_submit():
            user = User.query.filter_by(username=form.username.data).first()
            if not user:
                flash('未找到对应的用户，请确认用户名是否正确。', 'danger')
            else:
                tokens = (
                    PasswordResetToken.query.filter_by(user_id=user.id, used=False)
                    .order_by(PasswordResetToken.created_at.desc())
                    .all()
                )
                if not tokens:
                    flash('当前没有可用的重置令牌，请在服务器上生成新的令牌。', 'warning')
                else:
                    expired_token_updated = False
                    matching_token = None
                    for token in tokens:
                        if token.is_expired():
                            if not token.used:
                                token.used = True
                                expired_token_updated = True
                            continue
                        if token.verify(form.reset_token.data):
                            matching_token = token
                            break
                    if matching_token:
                        try:
                            user.set_password(form.new_password.data)
                            matching_token.mark_used()
                            db.session.commit()
                        except Exception as exc:
                            db.session.rollback()
                            current_app.logger.exception('重置密码失败: %s', exc)
                            flash('重置密码时出现错误，请稍后再试。', 'danger')
                        else:
                            flash('密码已成功重置，请使用新密码登录。', 'success')
                            return redirect(url_for('.login'))
                    else:
                        if expired_token_updated:
                            try:
                                db.session.commit()
                            except Exception as exc:
                                db.session.rollback()
                                current_app.logger.exception('更新令牌状态失败: %s', exc)
                        flash('重置令牌无效或已过期，请在服务器上生成新的令牌。', 'danger')
        elif form.is_submitted():
            flash('请修正表单中的错误后再提交。', 'danger')

        return self.render('admin/forgot_password.html', form=form)

    @expose('/logout')
    @login_required  # 最好也给 logout 加上保护
    def logout(self):
        logout_user()
        flash('您已成功退出登录。', 'info')
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


class MonitoringSettingsView(BaseView):
    menu_icon_type = 'fa'
    menu_icon_value = 'fa-sliders-h'

    @expose('/', methods=['GET', 'POST'])
    def index(self):
        if not current_user.is_authenticated:
            return redirect(url_for('admin.login', next=request.url))

        form = MonitoringSettingsForm()
        config_record = MonitoringConfig.ensure(current_app.config)
        field_labels = [
            ('monitor_interval_seconds', '监控间隔 (秒)'),
            ('slow_response_threshold_seconds', '慢响应阈值 (秒)'),
            ('slow_response_confirmation_threshold', '慢响应确认次数'),
            ('slow_response_window_size', '慢响应窗口大小'),
            ('slow_response_window_threshold', '慢响应窗口阈值'),
            ('slow_response_recovery_threshold', '慢响应恢复阈值'),
            ('failure_confirmation_threshold', '失败确认次数'),
            ('failure_window_size', '失败窗口大小'),
            ('failure_window_threshold', '失败窗口阈值'),
            ('recovery_confirmation_threshold', '恢复确认次数'),
            ('quick_retry_count', '快速重试次数'),
            ('quick_retry_delay_seconds', '快速重试间隔 (秒)'),
            ('data_retention_days', '数据保留天数')
        ]
        original_snapshot = {field: getattr(config_record, field) for field, _ in field_labels}

        def _format_config_value(value):
            if isinstance(value, float):
                return f"{value:.3f}".rstrip('0').rstrip('.')
            return value

        if not form.is_submitted():
            config_record.populate_form(form)

        changed_fields = []
        if form.validate_on_submit():
            try:
                config_record.update_from_form(form)
                changed_fields = [
                    (
                        label,
                        f"{_format_config_value(original_snapshot.get(field))} -> {_format_config_value(getattr(config_record, field))}"
                    )
                    for field, label in field_labels
                    if original_snapshot.get(field) != getattr(config_record, field)
                ]
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                current_app.logger.exception('保存监控参数失败: %s', exc)
                flash('保存监控参数失败，请稍后重试。', 'danger')
            else:
                config_record.apply_to_config(current_app.config)
                try:
                    job = scheduler.get_job('check_health_job')
                    if job:
                        job.reschedule(trigger='interval', seconds=current_app.config['MONITOR_INTERVAL_SECONDS'])
                except Exception as exc:
                    current_app.logger.warning('重新调度健康检查任务失败: %s', exc)
                if changed_fields:
                    operator = current_user.username if current_user.is_authenticated else None
                    send_management_notification('监控参数更新', operator=operator, details=changed_fields)
                flash('监控参数已更新。', 'success')
                return redirect(url_for('.index'))
        elif form.is_submitted():
            flash('请修正表单中的错误后再提交。', 'danger')

        return self.render(
            'admin/settings.html',
            form=form,
        )

    def is_accessible(self):
        return current_user.is_authenticated

    def _handle_view(self, name, **kwargs):
        if not self.is_accessible():
            return redirect(url_for('admin.login', next=request.url))


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

    def on_model_change(self, form, model, is_created):
        payload = None
        if is_created:
            payload = {
                'event': '新增监控站点',
                'details': [
                    ('网站名称', model.name),
                    ('监控地址', model.url),
                    ('初始状态', '启用' if model.is_active else '禁用')
                ]
            }
        else:
            state = sa_inspect(model)
            changes = []

            def _display(value):
                return '（空）' if value in (None, '') else value

            name_history = state.attrs.name.history
            if name_history.has_changes():
                old_value = name_history.deleted[0] if name_history.deleted else None
                changes.append(('网站名称变更', f"{_display(old_value)} -> {model.name}"))

            url_history = state.attrs.url.history
            if url_history.has_changes():
                old_value = url_history.deleted[0] if url_history.deleted else None
                changes.append(('监控地址变更', f"{_display(old_value)} -> {model.url}"))

            active_history = state.attrs.is_active.history
            if active_history.has_changes():
                old_value = active_history.deleted[0] if active_history.deleted else (not model.is_active)
                new_value = active_history.added[0] if active_history.added else model.is_active
                old_label = '启用' if bool(old_value) else '禁用'
                new_label = '启用' if bool(new_value) else '禁用'
                changes.append(('启用状态变更', f"{old_label} -> {new_label}"))

            if changes:
                details = [('当前网站名称', model.name)]
                details.extend(changes)
                payload = {'event': '更新监控站点', 'details': details}

        if payload:
            setattr(model, '_pending_admin_notification', payload)
        elif hasattr(model, '_pending_admin_notification'):
            delattr(model, '_pending_admin_notification')

        return super().on_model_change(form, model, is_created)

    def after_model_change(self, form, model, is_created):
        payload = getattr(model, '_pending_admin_notification', None)
        if payload and payload.get('details'):
            operator = current_user.username if current_user.is_authenticated else None
            send_management_notification(payload.get('event', '站点配置变更'), operator=operator, details=payload['details'])
            delattr(model, '_pending_admin_notification')
        return super().after_model_change(form, model, is_created)

    def after_model_delete(self, model):
        operator = current_user.username if current_user.is_authenticated else None
        send_management_notification(
            '删除监控站点',
            operator=operator,
            details=[('网站名称', model.name), ('监控地址', model.url)]
        )
        return super().after_model_delete(model)

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
    """
    提供历史监控数据的 API (最终版 v3.4: 在 Tooltip 中显示详细错误)
    """
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
    #查询所选站点中最早的数据时间
    if selected_sites:
        earliest_log = db.session.query(HealthCheckLog).filter(
            HealthCheckLog.site_name.in_(selected_sites)
        ).order_by(HealthCheckLog.timestamp.asc()).first()

        if earliest_log:
            earliest_data_time = earliest_log.timestamp.replace(tzinfo=timezone.utc)
            # 如果查询开始时间早于最早数据时间，自动调整
            if start_time_utc < earliest_data_time:
                original_start = start_time_utc
                start_time_utc = earliest_data_time
                current_app.logger.info(
                    f"[API] 时间范围自动调整: {original_start} -> {start_time_utc} "
                    f"(最早数据时间)"
                )
    results = {}
    monitor_interval = datetime.timedelta(seconds=current_app.config.get('MONITOR_INTERVAL_SECONDS', 60))

    for site in selected_sites:
        logs = db.session.query(HealthCheckLog).filter(
            HealthCheckLog.site_name == site,
            HealthCheckLog.timestamp.between(start_time_utc, end_time_utc)
        ).order_by(HealthCheckLog.timestamp.asc()).all()

        timeline_data = []

        def get_simple_status(log):
            if log.status == '无法访问': return 'down'
            if log.status == '访问过慢': return 'slow'
            return 'up'

        if not logs:
            timeline_data.append([
                int(start_time_utc.timestamp() * 1000),
                int(end_time_utc.timestamp() * 1000),
                0,
                "该时间段内无数据"
            ])
        else:
            i = 0
            while i < len(logs):
                current_log = logs[i]
                current_status = get_simple_status(current_log)

                if current_status == 'down':
                    start_ts = int(current_log.timestamp.replace(tzinfo=timezone.utc).timestamp() * 1000)
                    end_ts = start_ts + int(monitor_interval.total_seconds() * 1000)
                    reason = "未知错误"
                    if current_log.http_status_code and current_log.http_status_code >= 400:
                        reason = f"HTTP {current_log.http_status_code}"
                    elif current_log.error_detail:
                        reason = current_log.error_detail
                    details = f"状态: DOWN<br>原因: {reason}"
                    timeline_data.append([start_ts, end_ts, 3, details])
                    i += 1
                    continue

                j = i
                while j < len(logs) and get_simple_status(logs[j]) == current_status:
                    if j > i and (logs[j].timestamp - logs[j - 1].timestamp) > monitor_interval * 1.5:
                        break
                    j += 1
                segment_logs = logs[i:j]
                start_log = segment_logs[0]
                next_event_time = logs[j].timestamp if j < len(logs) else end_time_utc
                end_time = next_event_time.replace(tzinfo=timezone.utc)
                start_ts = int(start_log.timestamp.replace(tzinfo=timezone.utc).timestamp() * 1000)
                end_ts = int(end_time.timestamp() * 1000)
                status_map = {'up': 1, 'slow': 2}
                duration = end_time - start_log.timestamp.replace(tzinfo=timezone.utc)
                duration_str = str(duration).split('.')[0]
                avg_resp = sum(l.response_time_seconds for l in segment_logs) / len(segment_logs)
                details = f"状态: {current_status.upper()}<br>持续: {duration_str}<br>平均响应: {avg_resp:.3f}s"
                timeline_data.append([start_ts, end_ts, status_map[current_status], details])
                i = j

        # --- 为其他图表准备数据 ---
        up_count = sum(1 for log in logs if log.status in ['正常', '访问过慢'])
        availability = (up_count / len(logs) * 100) if logs else 0
        valid_times = [log.response_time_seconds for log in logs if log.response_time_seconds is not None]
        avg_response_time = sum(valid_times) / len(valid_times) if valid_times else 0

        results[site] = {
            "timeline_data": timeline_data,
            "overall_stats": {
                "availability": availability,
                "avg_response_time": avg_response_time
            },
            "response_times": {
                "timestamps": [to_gmt8(log.timestamp).strftime('%Y-%m-%d %H:%M') for log in logs],
                "times": [log.response_time_seconds for log in logs]
            }
        }
    return jsonify(results)
