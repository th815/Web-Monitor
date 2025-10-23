# web-monitor/app/__init__.py
import os

from flask import Flask
from flask_admin import Admin
from flask_admin.menu import MenuLink
from flask_login import LoginManager

from . import extensions
from .commands import create_reset_token_command, init_db_command
from .models import HealthCheckLog, MonitoredSite, MonitoringConfig, NotificationChannel, User
from .routes import (
    AuthenticatedMenuLink,
    HealthCheckLogView,
    MonitoringSettingsView,
    MonitoredSiteView,
    MyAdminIndexView,
    NotificationChannelView,
    ThemeSettingsView,
    main_bp,
)
from .services import check_website_health, cleanup_old_data


def create_app(config_object='config'):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object)
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # 2. 初始化插件
    extensions.db.init_app(app)
    extensions.migrate.init_app(app, extensions.db)

    # 3. 初始化 Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'admin.login'
    login_manager.login_message = '请登录后再访问此页面。'
    login_manager.login_message_category = 'warning'
    login_manager.needs_refresh_message = '会话已过期，请重新验证身份。'
    login_manager.needs_refresh_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # 4. 创建并配置一个全新的 Admin 实例
    extensions.admin = Admin(
        app,
        name='监控后台',
        template_mode='bootstrap4',
        base_template='admin/my_master_themed.html',
        index_view=MyAdminIndexView(name='后台主页')
    )
    extensions.admin.available_themes = [
        'Default', 'Cerulean', 'Cosmo', 'Cyborg', 'Darkly', 'Flatly',
        'Journal', 'Litera', 'Lumen', 'Lux', 'Materia', 'Minty', 'Pulse',
        'Sandstone', 'Simplex', 'Slate', 'Solar', 'Spacelab', 'United', 'Yeti'
    ]

    # 5. 添加所有导航项
    extensions.admin.add_view(MonitoredSiteView(MonitoredSite, extensions.db.session, name="站点管理"))
    extensions.admin.add_view(HealthCheckLogView(HealthCheckLog, extensions.db.session, name="监控日志"))
    extensions.admin.add_view(MonitoringSettingsView(name="监控参数", category="系统设置", endpoint='monitor_config'))
    extensions.admin.add_view(
        NotificationChannelView(
            NotificationChannel,
            extensions.db.session,
            name="通知渠道",
            category="系统设置",
            endpoint='notification_channels'
        )
    )

    extensions.admin.add_link(MenuLink(name='查看面板', url='/', icon_type='fa', icon_value='fa-desktop'))
    extensions.admin.add_view(ThemeSettingsView(name="更换主题", category="用户操作", endpoint='themes'))
    extensions.admin.add_link(MenuLink(name='修改密码', url='/admin/change-password', category='用户操作', icon_type='fa', icon_value='fa-key'))
    extensions.admin.add_link(AuthenticatedMenuLink(name='安全退出', endpoint='admin.logout', category='用户操作', icon_type='fa', icon_value='fa-sign-out'))

    # 6. 注册蓝图与自定义命令
    app.register_blueprint(main_bp)
    app.cli.add_command(init_db_command)
    app.cli.add_command(create_reset_token_command)

    # 7. 确保数据库与动态配置就绪
    with app.app_context():
        extensions.db.create_all()
        monitoring_config = MonitoringConfig.ensure(app.config)
        monitoring_config.apply_to_config(app.config)
        NotificationChannel.bootstrap_from_config(app.config)
    # 8. 配置和启动后台定时任务
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        if not extensions.scheduler.running:
            extensions.scheduler.init_app(app)
            extensions.scheduler.start()
            extensions.scheduler.add_job(
                id='check_health_job',
                func=check_website_health,
                trigger='interval',
                seconds=app.config.get('MONITOR_INTERVAL_SECONDS', 60),
                args=[app]
            )
            extensions.scheduler.add_job(
                id='cleanup_data_job',
                func=cleanup_old_data,
                trigger='cron', hour=3,
                args=[app]
            )
            print("后台监控任务已启动...")

    return app
