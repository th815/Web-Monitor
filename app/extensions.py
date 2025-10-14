from flask_sqlalchemy import SQLAlchemy
from flask_apscheduler import APScheduler
from flask_admin import Admin
from flask_migrate import Migrate
db = SQLAlchemy()
# 创建 APScheduler 实例
scheduler = APScheduler()
admin = Admin()
migrate = Migrate()