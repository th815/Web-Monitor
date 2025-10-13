# web-monitor/app/__init__.py
import os
from flask import Flask
from flask_login import LoginManager
from flask_admin import Admin
from flask_admin.menu import MenuLink
from . import extensions
from .models import User, MonitoredSite, HealthCheckLog
from .services import check_website_health, cleanup_old_data
from .routes import main_bp, MyAdminIndexView, MonitoredSiteView, HealthCheckLogView, AuthenticatedMenuLink, ThemeSettingsView
from .commands import init_db_command
def create_app(config_object='config'):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object)
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # 2. 初始化插件
    extensions.db.init_app(app)

    # 3. 初始化 Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'admin.login'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # 4. 创建并配置一个全新的 Admin 实例
    #    并用它覆盖掉 extensions.py 中那个空的 admin 实例
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

    # a. 核心功能视图
    extensions.admin.add_view(MonitoredSiteView(MonitoredSite, extensions.db.session, name="站点管理"))
    extensions.admin.add_view(HealthCheckLogView(HealthCheckLog, extensions.db.session, name="监控日志"))

    # b. 快捷链接
    extensions.admin.add_link(MenuLink(name='查看面板', url='/', icon_type='fa', icon_value='fa-desktop'))

    # c. 用户操作（放入下拉菜单）
    #    将 icon 参数移到 add_view 的参数列表中
    extensions.admin.add_view(ThemeSettingsView(name="更换主题", category="用户操作", endpoint='themes'))

    extensions.admin.add_link(MenuLink(name='修改密码', url='/admin/change-password', category='用户操作', icon_type='fa', icon_value='fa-key'))

    extensions.admin.add_link(AuthenticatedMenuLink(name='安全退出', endpoint='admin.logout', category='用户操作', icon_type='fa', icon_value='fa-sign-out'))

    # 5. 注册蓝图
    app.register_blueprint(main_bp)

    # 6. 注册自定义命令行
    app.cli.add_command(init_db_command)

    # 7. 配置和启动后台定时任务
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

    # 8. 在应用上下文中创建数据库表并执行首次检查
    with app.app_context():
        extensions.db.create_all()

        from .services import site_statuses
        if not site_statuses:
            print("首次执行健康检查以填充初始数据...")
            check_website_health()

    return app
