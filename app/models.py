import datetime
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
        self.data_retention_days = form.data_retention_days.data

    def __repr__(self):
        return f'<MonitoringConfig id={self.id} interval={self.monitor_interval_seconds}s>'
