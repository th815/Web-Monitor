## web-monitor/app/forms.py
from flask_wtf import FlaskForm
import json

from wtforms import (
    BooleanField,
    FloatField,
    IntegerField,
    PasswordField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, EqualTo, Length, NumberRange, Optional, URL, ValidationError


class LoginForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired()])
    password = PasswordField('密码', validators=[DataRequired()])
    remember_me = BooleanField('记住我')
    submit = SubmitField('登录')


class MonitoredSiteForm(FlaskForm):
    name = StringField('网站名称', validators=[DataRequired(message="请输入网站名称")])
    url = StringField('网站地址 (URL)', validators=[DataRequired(message="请输入URL"), URL(message="请输入有效的URL")])
    is_active = BooleanField('是否启用监控', default=True)


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('当前密码', validators=[DataRequired()])
    new_password = PasswordField(
        '新密码',
        validators=[
            DataRequired(),
            Length(min=8, message='新密码至少需要 8 个字符'),
            EqualTo('confirm_new_password', message='两次输入的密码不一致。'),
        ],
    )
    confirm_new_password = PasswordField('确认新密码', validators=[DataRequired()])
    submit = SubmitField('更新密码')


class PasswordResetForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired()])
    reset_token = StringField('重置令牌', validators=[DataRequired()])
    new_password = PasswordField(
        '新密码',
        validators=[
            DataRequired(),
            Length(min=8, message='新密码至少需要 8 个字符'),
            EqualTo('confirm_new_password', message='两次输入的密码不一致。'),
        ],
    )
    confirm_new_password = PasswordField('确认新密码', validators=[DataRequired()])
    submit = SubmitField('重置密码')


class MonitoringSettingsForm(FlaskForm):
    monitor_interval_seconds = IntegerField(
        '健康检查频率 (秒)',
        validators=[DataRequired(), NumberRange(min=10, max=86400, message='请输入 10-86400 之间的数值')],
    )
    slow_response_threshold_seconds = FloatField(
        '慢响应阈值 (秒)',
        validators=[DataRequired(), NumberRange(min=0.1, max=120, message='请输入 0.1-120 之间的数值')],
    )
    slow_response_confirmation_threshold = IntegerField(
        '慢响应连续判定次数', validators=[DataRequired(), NumberRange(min=1, max=50)]
    )
    slow_response_window_size = IntegerField(
        '慢响应窗口大小', validators=[DataRequired(), NumberRange(min=1, max=200)]
    )
    slow_response_window_threshold = IntegerField(
        '慢响应窗口触发次数', validators=[DataRequired(), NumberRange(min=1, max=200)]
    )
    slow_response_recovery_threshold = IntegerField(
        '慢响应恢复判定次数', validators=[DataRequired(), NumberRange(min=1, max=50)]
    )
    failure_confirmation_threshold = IntegerField(
        '宕机连续判定次数', validators=[DataRequired(), NumberRange(min=1, max=50)]
    )
    failure_window_size = IntegerField('宕机窗口大小', validators=[DataRequired(), NumberRange(min=1, max=200)])
    failure_window_threshold = IntegerField(
        '宕机窗口触发次数', validators=[DataRequired(), NumberRange(min=1, max=200)]
    )
    recovery_confirmation_threshold = IntegerField(
        '宕机恢复判定次数', validators=[DataRequired(), NumberRange(min=1, max=50)]
    )
    quick_retry_count = IntegerField(
        '失败快速重试次数', validators=[DataRequired(), NumberRange(min=0, max=10)]
    )
    quick_retry_delay_seconds = IntegerField(
        '快速重试间隔 (秒)', validators=[DataRequired(), NumberRange(min=0, max=60)]
    )
    data_retention_days = IntegerField(
        '数据保留天数', validators=[DataRequired(), NumberRange(min=1, max=30)]
    )
    submit = SubmitField('保存设置')


class NotificationSettingsForm(FlaskForm):
    webhook_enabled = BooleanField('启用 Webhook 通知')
    webhook_url = StringField(
        'Webhook 地址',
        validators=[Optional(), URL(message='请输入有效的 URL 地址')]
    )
    webhook_content_type = StringField(
        '内容类型',
        validators=[Optional(), Length(max=120)],
        default='application/json'
    )
    webhook_headers = TextAreaField(
        '自定义请求头 (JSON)',
        validators=[Optional()],
        render_kw={'placeholder': '{"Authorization": "Bearer your-token"}'}
    )
    webhook_template = TextAreaField(
        '消息模板',
        validators=[Optional(), Length(max=8000)],
        render_kw={'rows': 15}
    )
    submit = SubmitField('保存设置')
    test_webhook = SubmitField('发送测试通知')

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False

        if self.webhook_enabled.data:
            if not self.webhook_url.data:
                self.webhook_url.errors.append('启用 Webhook 时必须填写地址。')
                return False
            if not self.webhook_template.data:
                self.webhook_template.errors.append('启用 Webhook 时必须提供模板。')
                return False

        return True

    def validate_webhook_headers(self, field):
        if not field.data or not field.data.strip():
            return
        try:
            value = json.loads(field.data)
        except (TypeError, json.JSONDecodeError):
            raise ValidationError('请求头需要是有效的 JSON 对象，例如 {"Authorization": "Bearer xxx"}')
        if not isinstance(value, dict):
            raise ValidationError('请求头必须是一个 JSON 对象，例如 {"Authorization": "Bearer xxx"}')

