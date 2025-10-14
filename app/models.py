import datetime
from .extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


# UserMixin 提供了 Flask-Login 需要的所有用户属性和方法
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(128))

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
