from flask_sqlalchemy import SQLAlchemy
from flask_apscheduler import APScheduler
from flask_admin import Admin
db = SQLAlchemy()
# 创建 APScheduler 实例
scheduler = APScheduler()
admin = Admin()