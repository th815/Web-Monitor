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
    NotificationChannelForm,
    PasswordResetForm,
)
from .models import (
    HealthCheckLog,
    MonitoringConfig,
    MonitoredSite,
    NotificationChannel,
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
            ('alert_suppression_seconds', '告警降噪周期 (秒)'),
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

class NotificationChannelView(SecureModelView):
    menu_icon_type = 'fa'
    menu_icon_value = 'fa-bell'
    form = NotificationChannelForm
    can_view_details = True
    column_list = [
        'name',
        'channel_type',
        'is_enabled',
        'webhook_url',
        'notify_on_down',
        'notify_on_recovered',
        'notify_on_slow',
        'notify_on_slow_recovered',
        'notify_on_management',
        'created_at',
    ]
    column_details_list = [
        'name',
        'channel_type',
        'is_enabled',
        'webhook_url',
        'notify_on_down',
        'notify_on_recovered',
        'notify_on_slow',
        'notify_on_slow_recovered',
        'notify_on_management',
        'custom_headers',
        'custom_template',
        'created_at',
        'updated_at',
    ]
    column_labels = {
        'name': '渠道名称',
        'channel_type': '渠道类型',
        'is_enabled': '启用',
        'webhook_url': 'Webhook 地址',
        'notify_on_down': '宕机',
        'notify_on_recovered': '恢复',
        'notify_on_slow': '慢响应',
        'notify_on_slow_recovered': '慢响应恢复',
        'notify_on_management': '配置变更',
        'custom_headers': '自定义请求头',
        'custom_template': '消息模板',
        'created_at': '创建时间',
        'updated_at': '更新时间',
    }
    column_filters = ['channel_type', 'is_enabled']
    column_searchable_list = ['name', 'webhook_url']
    form_excluded_columns = ['created_at', 'updated_at']
    column_default_sort = ('created_at', True)
    column_formatters = {
        'channel_type': lambda view, context, model, name: NotificationChannelView.CHANNEL_TYPE_LABELS.get(
            model.channel_type, model.channel_type
        ),
        'created_at': format_datetime_gmt8,
        'updated_at': format_datetime_gmt8,
    }

    CHANNEL_TYPE_LABELS = {
        NotificationChannel.TYPE_QYWECHAT: '企业微信',
        NotificationChannel.TYPE_DINGTALK: '钉钉',
        NotificationChannel.TYPE_FEISHU: '飞书',
        NotificationChannel.TYPE_CUSTOM: '自定义 Webhook',
    }

    def create_form(self, obj=None):
        form = super().create_form(obj)
        if not form.custom_template.data:
            form.custom_template.data = NotificationChannel.default_custom_template()
        return form

    def on_form_prefill(self, form, id):
        channel = self.get_one(id)
        if channel:
            headers = channel.custom_headers or {}
            form.custom_headers.data = json.dumps(headers, ensure_ascii=False, indent=2) if headers else ''
            if channel.channel_type == NotificationChannel.TYPE_CUSTOM:
                form.custom_template.data = channel.custom_template or NotificationChannel.default_custom_template()
            else:
                form.custom_template.data = ''
        return super().on_form_prefill(form, id)

    def on_model_change(self, form, model, is_created):
        raw_headers = form.custom_headers.data or ''
        if raw_headers.strip():
            model.custom_headers = json.loads(raw_headers)
        else:
            model.custom_headers = {}
        model.webhook_url = (form.webhook_url.data or '').strip() or None
        if model.channel_type == NotificationChannel.TYPE_CUSTOM:
            template = (form.custom_template.data or '').strip()
            model.custom_template = template or NotificationChannel.default_custom_template()
        else:
            model.custom_template = None
        return super().on_model_change(form, model, is_created)

    def after_model_change(self, form, model, is_created):
        operator = current_user.username if current_user.is_authenticated else None
        action = '创建' if is_created else '更新'
        events = [
            ('宕机', model.notify_on_down),
            ('恢复', model.notify_on_recovered),
            ('慢响应', model.notify_on_slow),
            ('慢响应恢复', model.notify_on_slow_recovered),
            ('配置变更', model.notify_on_management),
        ]
        enabled_events = [label for label, enabled in events if enabled]
        details = [
            ('渠道名称', model.name),
            ('渠道类型', self.CHANNEL_TYPE_LABELS.get(model.channel_type, model.channel_type)),
            ('启用状态', '启用' if model.is_enabled else '禁用'),
            ('通知事件', '、'.join(enabled_events) if enabled_events else '无'),
            ('Webhook 地址', model.webhook_url or '未配置'),
        ]
        send_management_notification(f'通知渠道{action}', operator=operator, details=details)
        return super().after_model_change(form, model, is_created)

    def after_model_delete(self, model):
        operator = current_user.username if current_user.is_authenticated else None
        details = [
            ('渠道名称', model.name),
            ('渠道类型', self.CHANNEL_TYPE_LABELS.get(model.channel_type, model.channel_type)),
        ]
        send_management_notification('删除通知渠道', operator=operator, details=details)
        return super().after_model_delete(model)


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
        incidents = []

        def get_simple_status(log):
            if log.status == '无法访问': return 'down'
            if log.status == '访问过慢': return 'slow'
            return 'up'

        def extract_incident_reason(log):
            if log.error_detail:
                return log.error_detail
            if log.http_status_code and log.http_status_code >= 400:
                return f"HTTP {log.http_status_code}"
            if log.status == '访问过慢' and log.response_time_seconds is not None:
                return f"响应时间 {log.response_time_seconds:.3f}s"
            return None

        status_label_map = {'down': '宕机', 'slow': '访问过慢'}
        current_incident = None

        def finalize_incident(incident, closure_time, resolved):
            if not incident:
                return
            resolved_time = min(closure_time, end_time_utc)
            if resolved_time < incident['start']:
                resolved_time = incident['start']
            duration_ms = max(0, int((resolved_time - incident['start']).total_seconds() * 1000))
            reason = next((candidate for candidate in incident.get('reasons', []) if candidate), None)
            incidents.append({
                "status_key": incident['status'],
                "status_label": status_label_map.get(incident['status'], incident['status']),
                "start_ts": int(incident['start'].timestamp() * 1000),
                "end_ts": int(resolved_time.timestamp() * 1000),
                "duration_ms": duration_ms,
                "resolved": resolved,
                "reason": reason,
                "http_status_code": incident.get('http_status_code'),
            })

        if not logs:
            timeline_data.append([
                int(start_time_utc.timestamp() * 1000),
                int(end_time_utc.timestamp() * 1000),
                0,
                "该时间段内无数据"
            ])
        else:
            for log in logs:
                status_key = get_simple_status(log)
                log_time = log.timestamp.replace(tzinfo=timezone.utc)
                reason = extract_incident_reason(log)

                if status_key in ('down', 'slow'):
                    if current_incident and current_incident['status'] == status_key:
                        current_incident['last_seen'] = log_time
                        if reason and reason not in current_incident['reasons']:
                            current_incident['reasons'].append(reason)
                        if log.http_status_code and not current_incident.get('http_status_code'):
                            current_incident['http_status_code'] = log.http_status_code
                    else:
                        if current_incident:
                            finalize_incident(current_incident, log_time, True)
                        current_incident = {
                            "status": status_key,
                            "start": log_time,
                            "last_seen": log_time,
                            "reasons": [reason] if reason else [],
                            "http_status_code": log.http_status_code if log.http_status_code else None,
                        }
                else:
                    if current_incident:
                        finalize_incident(current_incident, log_time, True)
                        current_incident = None

            if current_incident:
                finalize_incident(current_incident, end_time_utc, False)

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
        
        # 计算 P95 和 P99
        p95_response_time = 0
        p99_response_time = 0
        if valid_times:
            sorted_times = sorted(valid_times)
            p95_index = int(len(sorted_times) * 0.95)
            p99_index = int(len(sorted_times) * 0.99)
            p95_response_time = sorted_times[min(p95_index, len(sorted_times) - 1)]
            p99_response_time = sorted_times[min(p99_index, len(sorted_times) - 1)]

        response_points = []
        for log in logs:
            gmt8_timestamp = to_gmt8(log.timestamp)
            timestamp_str = gmt8_timestamp.strftime('%Y-%m-%d %H:%M') if gmt8_timestamp else ''
            timestamp_ms = int(gmt8_timestamp.timestamp() * 1000) if gmt8_timestamp else None
            response_points.append((timestamp_str, timestamp_ms, log.response_time_seconds))

        # 计算 SLA 统计（今日、近7天、近30天）
        now_utc = datetime.datetime.now(timezone.utc)
        today_start = datetime.datetime.combine(now_utc.date(), datetime.time.min, tzinfo=timezone.utc)
        week_start = now_utc - datetime.timedelta(days=7)
        month_start = now_utc - datetime.timedelta(days=30)
        
        def calc_availability_for_period(period_start, period_end):
            period_logs = [log for log in logs if period_start <= log.timestamp.replace(tzinfo=timezone.utc) <= period_end]
            if not period_logs:
                return availability  # 如果没有数据，返回整体可用率
            period_up_count = sum(1 for log in period_logs if log.status in ['正常', '访问过慢'])
            return (period_up_count / len(period_logs) * 100) if period_logs else 0
        
        sla_today = calc_availability_for_period(today_start, now_utc)
        sla_week = calc_availability_for_period(week_start, now_utc)
        sla_month = calc_availability_for_period(month_start, now_utc)

        results[site] = {
            "timeline_data": timeline_data,
            "overall_stats": {
                "availability": availability,
                "avg_response_time": avg_response_time,
                "p95_response_time": p95_response_time,
                "p99_response_time": p99_response_time
            },
            "response_times": {
                "timestamps": [point[0] for point in response_points],
                "timestamps_ms": [point[1] for point in response_points],
                "times": [point[2] for point in response_points]
            },
            "incidents": incidents,
            "sla_stats": {
                "today": sla_today,
                "week": sla_week,
                "month": sla_month
            }
        }
    return jsonify(results)
