# web-monitor/app/commands.py
import click
from flask.cli import with_appcontext
from .extensions import db
from .models import User, MonitoredSite
from .services import check_website_health  # 【新增】导入健康检查函数


@click.command('init-db')
@with_appcontext
def init_db_command():
    """
    初始化数据库：创建所有表，并添加默认数据，然后执行首次健康检查。
    """
    db.create_all()

    default_password = 'changeme'
    if not User.query.first():
        click.echo('正在创建默认管理员账户...')
        default_admin = User(username='admin')
        default_admin.set_password(default_password)
        db.session.add(default_admin)
        click.echo(f"  - 用户名: admin, 密码: {default_password}")
    else:
        click.echo('管理员账户已存在，跳过创建。')
    if not MonitoredSite.query.first():
        click.echo('正在添加默认的监控站点列表...')
        default_sites = [
            {"name": "谷歌", "url": "https://www.google.com"},
            {"name": "GitHub", "url": "https://www.github.com"},
            {"name": "ERP系统", "url": "https://erp.huimaisoft.com"},
            {"name": "SCM系统", "url": "https://scm-pc.huimaisoft.com"},
            {"name": "不存在的网站", "url": "http://thiswebsitedoesnotexist.com"},
            {"name": "响应慢的网站", "url": "http://httpbin.org/delay/5"},
        ]
        for site_data in default_sites:
            site = MonitoredSite(name=site_data['name'], url=site_data['url'])
            db.session.add(site)
            click.echo(f"  - 添加站点: {site_data['name']}")
    else:
        click.echo('监控站点已存在，跳过创建。')
    db.session.commit()

    # 【核心修改】在数据提交后，手动调用一次健康检查
    click.echo('=' * 40)
    click.echo('数据库和初始数据已准备就绪。')
    click.echo('正在执行首次健康检查以填充状态...')
    check_website_health()  # 直接调用
    click.echo('=' * 40)

    click.echo('数据库初始化完成！')
    click.echo(f"已创建默认管理员账户 (如果不存在):")
    click.echo(f"  用户名: admin")
    click.echo(f"  密  码: {default_password}")
    click.echo('请在首次登录后立即修改密码！')
    click.echo('=' * 40)

