# web-monitor/app/commands.py
import click
from flask.cli import with_appcontext
from .extensions import db
from .models import User, MonitoredSite


# 使用 @click.command() 创建一个名为 'init-db' 的命令
@click.command('init-db')
@with_appcontext
def init_db_command():
    """
    初始化数据库：创建所有表，并添加默认数据（管理员和监控站点）。
    """
    # 首先确保所有表都已创建
    db.create_all()
    # --- 初始化管理员 ---
    if User.query.first():
        click.echo('管理员账户已存在，跳过创建。')
    else:
        click.echo('正在创建默认管理员账户...')
        default_admin = User(username='admin')
        default_password = 'changeme'  # 建议首次登录后修改
        default_admin.set_password(default_password)
        db.session.add(default_admin)
        click.echo(f"  - 用户名: admin, 密码: {default_password}")
    # --- 初始化默认监控站点 ---
    if MonitoredSite.query.first():
        click.echo('监控站点已存在，跳过创建。')
    else:
        click.echo('正在添加默认的监控站点列表...')
        # 这就是你原来 config.py 里的列表
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

    # 一次性提交所有更改
    db.session.commit()
    click.echo('=' * 40)
    click.echo('数据库初始化完成！')
    click.echo('=' * 40)
    click.echo('初始化成功！')
    click.echo(f"已创建默认管理员账户:")
    click.echo(f"  用户名: admin")
    click.echo(f"  密  码: {default_password}")
    click.echo('请在首次登录后立即修改密码！')
    click.echo('=' * 40)

