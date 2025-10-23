# web-monitor/app/models.py
import datetime
import json
from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.ext.mutable import MutableDict
from werkzeug.security import generate_password_hash, check_password_hash

from .extensions import db
from flask_login import UserMixin


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    password_reset_tokens = db.relationship(
        'PasswordResetToken', backref='user', lazy='dynamic', cascade='all, delete-orphan'
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


class MonitoredSite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    url = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    def to_dict(self):
        return {'name': self.name, 'url': self.url}

    def __repr__(self):
        return f'<MonitoredSite {self.name}>'


class HealthCheckLog(db.Model):
    __tablename__ = 'health_check_log'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    site_name = db.Column(db.String, nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)
    status = db.Column(db.String, nullable=False)
    response_time_seconds = db.Column(db.Float)
    http_status_code = db.Column(db.Integer, nullable=True)
    error_detail = db.Column(db.String(500), nullable=True)

    def __repr__(self):
        return f'<HealthCheckLog {self.site_name} at {self.timestamp}>'


class PasswordResetToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    token_hash = db.Column(db.String(256), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)

    def is_expired(self):
        return datetime.datetime.utcnow() > self.expires_at

    def verify(self, raw_token: str) -> bool:
        if not raw_token:
            return False
        if self.used or self.is_expired():
            return False
        return check_password_hash(self.token_hash, raw_token)

    def mark_used(self):
        self.used = True

    def __repr__(self):
        status = 'used' if self.used else 'active'
        return f'<PasswordResetToken user={self.user_id} status={status}>'


class MonitoringConfig(db.Model):
    __tablename__ = 'monitoring_config'
    id = db.Column(db.Integer, primary_key=True)
    monitor_interval_seconds = db.Column(db.Integer, nullable=False, default=20)
    slow_response_threshold_seconds = db.Column(db.Float, nullable=False, default=3.0)
    slow_response_confirmation_threshold = db.Column(db.Integer, nullable=False, default=3)
    slow_response_window_size = db.Column(db.Integer, nullable=False, default=5)
    slow_response_window_threshold = db.Column(db.Integer, nullable=False, default=3)
    slow_response_recovery_threshold = db.Column(db.Integer, nullable=False, default=2)
    failure_confirmation_threshold = db.Column(db.Integer, nullable=False, default=3)
    failure_window_size = db.Column(db.Integer, nullable=False, default=5)
    failure_window_threshold = db.Column(db.Integer, nullable=False, default=3)
    recovery_confirmation_threshold = db.Column(db.Integer, nullable=False, default=2)
    quick_retry_count = db.Column(db.Integer, nullable=False, default=1)
    quick_retry_delay_seconds = db.Column(db.Integer, nullable=False, default=2)
    alert_suppression_seconds = db.Column(db.Integer, nullable=False, default=600)
    data_retention_days = db.Column(db.Integer, nullable=False, default=30)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )

    @classmethod
    def ensure(cls, fallback_config: dict):
        instance = cls.query.first()
        if not instance:
            raw_alert_suppression = fallback_config.get('ALERT_SUPPRESSION_SECONDS', 600)
            try:
                alert_suppression_value = int(raw_alert_suppression)
            except (TypeError, ValueError):
                alert_suppression_value = 600
            alert_suppression_value = max(0, alert_suppression_value)

            instance = cls(
                monitor_interval_seconds=fallback_config.get('MONITOR_INTERVAL_SECONDS', 20),
                slow_response_threshold_seconds=fallback_config.get(
                    'SLOW_RESPONSE_THRESHOLD_SECONDS', fallback_config.get('SLOW_RESPONSE_THRESHOLD', 3.0)
                ),
                slow_response_confirmation_threshold=fallback_config.get('SLOW_RESPONSE_CONFIRMATION_THRESHOLD', 3),
                slow_response_window_size=fallback_config.get('SLOW_RESPONSE_WINDOW_SIZE', 5),
                slow_response_window_threshold=fallback_config.get('SLOW_RESPONSE_WINDOW_THRESHOLD', 3),
                slow_response_recovery_threshold=fallback_config.get('SLOW_RESPONSE_RECOVERY_THRESHOLD', 2),
                failure_confirmation_threshold=fallback_config.get('FAILURE_CONFIRMATION_THRESHOLD', 3),
                failure_window_size=fallback_config.get('FAILURE_WINDOW_SIZE', 5),
                failure_window_threshold=fallback_config.get('FAILURE_WINDOW_THRESHOLD', 3),
                recovery_confirmation_threshold=fallback_config.get('RECOVERY_CONFIRMATION_THRESHOLD', 2),
                quick_retry_count=fallback_config.get('QUICK_RETRY_COUNT', 1),
                quick_retry_delay_seconds=fallback_config.get('QUICK_RETRY_DELAY_SECONDS', 2),
                alert_suppression_seconds=alert_suppression_value,
                data_retention_days=fallback_config.get('DATA_RETENTION_DAYS', 30),
            )
            db.session.add(instance)
            db.session.commit()
        return instance

    def apply_to_config(self, app_config: dict):
        app_config['MONITOR_INTERVAL_SECONDS'] = self.monitor_interval_seconds
        app_config['SLOW_RESPONSE_THRESHOLD_SECONDS'] = self.slow_response_threshold_seconds
        app_config['SLOW_RESPONSE_CONFIRMATION_THRESHOLD'] = self.slow_response_confirmation_threshold
        app_config['SLOW_RESPONSE_WINDOW_SIZE'] = self.slow_response_window_size
        app_config['SLOW_RESPONSE_WINDOW_THRESHOLD'] = self.slow_response_window_threshold
        app_config['SLOW_RESPONSE_RECOVERY_THRESHOLD'] = self.slow_response_recovery_threshold
        app_config['FAILURE_CONFIRMATION_THRESHOLD'] = self.failure_confirmation_threshold
        app_config['FAILURE_WINDOW_SIZE'] = self.failure_window_size
        app_config['FAILURE_WINDOW_THRESHOLD'] = self.failure_window_threshold
        app_config['RECOVERY_CONFIRMATION_THRESHOLD'] = self.recovery_confirmation_threshold
        app_config['QUICK_RETRY_COUNT'] = self.quick_retry_count
        app_config['QUICK_RETRY_DELAY_SECONDS'] = self.quick_retry_delay_seconds
        app_config['ALERT_SUPPRESSION_SECONDS'] = self.alert_suppression_seconds
        app_config['DATA_RETENTION_DAYS'] = self.data_retention_days

    def populate_form(self, form):
        form.monitor_interval_seconds.data = self.monitor_interval_seconds
        form.slow_response_threshold_seconds.data = self.slow_response_threshold_seconds
        form.slow_response_confirmation_threshold.data = self.slow_response_confirmation_threshold
        form.slow_response_window_size.data = self.slow_response_window_size
        form.slow_response_window_threshold.data = self.slow_response_window_threshold
        form.slow_response_recovery_threshold.data = self.slow_response_recovery_threshold
        form.failure_confirmation_threshold.data = self.failure_confirmation_threshold
        form.failure_window_size.data = self.failure_window_size
        form.failure_window_threshold.data = self.failure_window_threshold
        form.recovery_confirmation_threshold.data = self.recovery_confirmation_threshold
        form.quick_retry_count.data = self.quick_retry_count
        form.quick_retry_delay_seconds.data = self.quick_retry_delay_seconds
        form.alert_suppression_seconds.data = self.alert_suppression_seconds
        form.data_retention_days.data = self.data_retention_days

    def update_from_form(self, form):
        self.monitor_interval_seconds = form.monitor_interval_seconds.data
        self.slow_response_threshold_seconds = form.slow_response_threshold_seconds.data
        self.slow_response_confirmation_threshold = form.slow_response_confirmation_threshold.data
        self.slow_response_window_size = form.slow_response_window_size.data
        self.slow_response_window_threshold = form.slow_response_window_threshold.data
        self.slow_response_recovery_threshold = form.slow_response_recovery_threshold.data
        self.failure_confirmation_threshold = form.failure_confirmation_threshold.data
        self.failure_window_size = form.failure_window_size.data
        self.failure_window_threshold = form.failure_window_threshold.data
        self.recovery_confirmation_threshold = form.recovery_confirmation_threshold.data
        self.quick_retry_count = form.quick_retry_count.data
        self.quick_retry_delay_seconds = form.quick_retry_delay_seconds.data
        self.alert_suppression_seconds = form.alert_suppression_seconds.data
        self.data_retention_days = form.data_retention_days.data

    def __repr__(self):
        return f'<MonitoringConfig id={self.id} interval={self.monitor_interval_seconds}s>'


class NotificationChannel(db.Model):
    __tablename__ = 'notification_channel'

    TYPE_QYWECHAT = 'qywechat'
    TYPE_DINGTALK = 'dingtalk'
    TYPE_FEISHU = 'feishu'
    TYPE_CUSTOM = 'custom'

    EVENT_FIELD_MAP = {
        'down': 'notify_on_down',
        'recovered': 'notify_on_recovered',
        'slow': 'notify_on_slow',
        'slow_recovered': 'notify_on_slow_recovered',
        'management': 'notify_on_management',
    }

    DEFAULT_CUSTOM_TEMPLATE = """{
  "event": "{{ event }}",
  "title": "{{ event_title }}",
  "site": {
    "name": "{{ site_name }}",
    "url": "{{ site_url }}"
  },
  "status": {
    "key": "{{ status_key }}",
    "label": "{{ status_label }}",
    "previous": "{{ previous_status }}"
  },
  "severity": "{{ severity|default('info') }}",
  "operator": "{{ operator|default('') }}",
  "timestamp": "{{ timestamp }}",
  "http_code": {{ http_code|default('null') }},
  "error_detail": {{ error_detail|tojson }},
  "extra": {{ details|tojson }}
}"""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    channel_type = db.Column(db.String(32), nullable=False, index=True)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True, index=True)
    webhook_url = db.Column(db.String(512), nullable=True)
    notify_on_down = db.Column(db.Boolean, nullable=False, default=True)
    notify_on_recovered = db.Column(db.Boolean, nullable=False, default=True)
    notify_on_slow = db.Column(db.Boolean, nullable=False, default=False)
    notify_on_slow_recovered = db.Column(db.Boolean, nullable=False, default=False)
    notify_on_management = db.Column(db.Boolean, nullable=False, default=False)
    custom_headers = db.Column(MutableDict.as_mutable(db.JSON), nullable=False, default=dict)
    custom_template = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        db.Index('ix_notification_channel_type_enabled', 'channel_type', 'is_enabled'),
    )

    @staticmethod
    def default_custom_template():
        return NotificationChannel.DEFAULT_CUSTOM_TEMPLATE

    def headers_dict(self):
        return dict(self.custom_headers or {})

    def to_message_config(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'channel_type': self.channel_type,
            'is_enabled': self.is_enabled,
            'webhook_url': self.webhook_url,
            'notify_on_down': self.notify_on_down,
            'notify_on_recovered': self.notify_on_recovered,
            'notify_on_slow': self.notify_on_slow,
            'notify_on_slow_recovered': self.notify_on_slow_recovered,
            'notify_on_management': self.notify_on_management,
            'custom_headers': self.headers_dict(),
            'custom_template': self.custom_template,
        }

    def should_notify(self, event_key: str) -> bool:
        field_name = self.EVENT_FIELD_MAP.get(event_key)
        if not field_name:
            return False
        return bool(getattr(self, field_name, False))

    @classmethod
    def _generate_unique_name(cls, base_name: str) -> str:
        candidate = base_name
        counter = 1
        while cls.query.filter_by(name=candidate).first() is not None:
            counter += 1
            candidate = f"{base_name} {counter}"
        return candidate

    @classmethod
    def _bootstrap_from_legacy_config(cls) -> bool:
        inspector = sa_inspect(db.engine)
        if 'notification_config' not in inspector.get_table_names():
            return False
        result = db.session.execute(
            text(
                'SELECT webhook_enabled, webhook_url, webhook_headers, webhook_template '
                'FROM notification_config ORDER BY id ASC LIMIT 1'
            )
        ).mappings().first()
        if not result:
            return False
        if not result['webhook_enabled'] or not result['webhook_url']:
            return False
        headers = {}
        raw_headers = result['webhook_headers']
        if raw_headers:
            try:
                loaded_headers = json.loads(raw_headers)
                if isinstance(loaded_headers, dict):
                    headers = loaded_headers
            except (TypeError, ValueError):
                headers = {}
        template_text = result['webhook_template'] or cls.DEFAULT_CUSTOM_TEMPLATE
        existing = (
            cls.query.filter_by(channel_type=cls.TYPE_CUSTOM, webhook_url=result['webhook_url']).first()
        )
        if existing:
            return False
        name = cls._generate_unique_name('迁移的 Webhook 渠道')
        channel = cls(
            name=name,
            channel_type=cls.TYPE_CUSTOM,
            webhook_url=result['webhook_url'],
            is_enabled=True,
            notify_on_down=True,
            notify_on_recovered=True,
            notify_on_slow=True,
            notify_on_slow_recovered=True,
            notify_on_management=True,
            custom_headers=headers,
            custom_template=template_text,
        )
        db.session.add(channel)
        return True

    @classmethod
    def bootstrap_from_config(cls, app_config) -> bool:
        created = False
        # 迁移旧的单通道配置
        if cls._bootstrap_from_legacy_config():
            created = True

        qy_url = (app_config or {}).get('QYWECHAT_WEBHOOK_URL')
        if qy_url and "YOUR_KEY_HERE" not in qy_url:
            existing_qy = cls.query.filter_by(channel_type=cls.TYPE_QYWECHAT).first()
            if not existing_qy:
                name = cls._generate_unique_name('默认企业微信渠道')
                channel = cls(
                    name=name,
                    channel_type=cls.TYPE_QYWECHAT,
                    webhook_url=qy_url,
                    is_enabled=True,
                    notify_on_down=True,
                    notify_on_recovered=True,
                    notify_on_slow=True,
                    notify_on_slow_recovered=True,
                    notify_on_management=True,
                )
                db.session.add(channel)
                created = True

        generic_enabled = (app_config or {}).get('GENERIC_WEBHOOK_ENABLED')
        generic_url = (app_config or {}).get('GENERIC_WEBHOOK_URL')
        if generic_enabled and generic_url:
            existing_generic = cls.query.filter_by(
                channel_type=cls.TYPE_CUSTOM, webhook_url=generic_url
            ).first()
            if not existing_generic:
                headers = app_config.get('GENERIC_WEBHOOK_HEADERS') or {}
                name = cls._generate_unique_name('默认自定义渠道')
                channel = cls(
                    name=name,
                    channel_type=cls.TYPE_CUSTOM,
                    webhook_url=generic_url,
                    is_enabled=True,
                    notify_on_down=True,
                    notify_on_recovered=True,
                    notify_on_slow=True,
                    notify_on_slow_recovered=True,
                    notify_on_management=True,
                    custom_headers=headers if isinstance(headers, dict) else {},
                    custom_template=app_config.get('GENERIC_WEBHOOK_TEMPLATE')
                    or cls.DEFAULT_CUSTOM_TEMPLATE,
                )
                db.session.add(channel)
                created = True

        if created:
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise
        return created

    def __repr__(self):
        return f"<NotificationChannel id={self.id} name={self.name} type={self.channel_type}>"
