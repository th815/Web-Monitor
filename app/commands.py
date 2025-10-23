# web-monitor/app/commands.py
import datetime
import secrets

import click
from flask import current_app
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash

from .extensions import db
from .models import MonitoringConfig, MonitoredSite, NotificationChannel, PasswordResetToken, User
from .services import check_website_health  # 【新增】导入健康检查函数


@click.command('init-db')
@with_appcontext
def init_db_command():
    """
    初始化数据库：创建所有表，并添加默认数据，然后执行首次健康检查。
    """
    db.create_all()

    MonitoringConfig.ensure(current_app.config)
    channels_from_config = NotificationChannel.bootstrap_from_config(current_app.config)

    default_password = 'admin123'
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
            {"name": "百度", "url": "https://www.baidu.com"},
            {"name": "不存在的网站", "url": "http://tianhaozuishuai.com"},
            {"name": "响应慢的网站", "url": "http://httpbin.org/delay/5"},
        ]
        for site_data in default_sites:
            site = MonitoredSite(name=site_data['name'], url=site_data['url'])
            db.session.add(site)
            click.echo(f"  - 添加站点: {site_data['name']}")
    else:
        click.echo('监控站点已存在，跳过创建。')

    if channels_from_config:
        click.echo('已根据配置文件导入通知渠道。')

    if NotificationChannel.query.count() == 0:
        sample_channel = NotificationChannel(
            name='示例自定义渠道',
            channel_type=NotificationChannel.TYPE_CUSTOM,
            is_enabled=False,
            webhook_url=None,
            notify_on_down=True,
            notify_on_recovered=True,
            notify_on_slow=True,
            notify_on_slow_recovered=True,
            notify_on_management=True,
            custom_headers={},
            custom_template=NotificationChannel.default_custom_template(),
        )
        db.session.add(sample_channel)
        click.echo('已创建一个禁用的示例通知渠道，便于后续配置。')

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


@click.command('create-reset-token')
@click.argument('username')
@click.option('--expires-in', default=3600, show_default=True, help='令牌有效期（秒）')
@with_appcontext
def create_reset_token_command(username, expires_in):
    """为指定用户创建一次性密码重置令牌。"""
    if expires_in <= 0:
        raise click.BadParameter('expires-in 必须大于 0', param='expires_in')

    user = User.query.filter_by(username=username).first()
    if not user:
        click.echo(f'未找到用户名为 {username} 的用户。')
        return

    now = datetime.datetime.utcnow()
    expiration = now + datetime.timedelta(seconds=expires_in)

    # 让已有的活动令牌失效，确保同一时间仅有一个有效令牌
    active_tokens = PasswordResetToken.query.filter_by(user_id=user.id, used=False).all()
    for token in active_tokens:
        if token.is_expired():
            token.used = True
        else:
            token.used = True
    raw_token = secrets.token_urlsafe(24)
    token_entry = PasswordResetToken(
        user=user,
        token_hash=generate_password_hash(raw_token),
        expires_at=expiration,
    )
    db.session.add(token_entry)
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise click.ClickException(f'创建重置令牌失败: {exc}')

    click.echo('=' * 60)
    click.echo(f'用户 {username} 的一次性重置令牌已创建。')
    click.echo(f'令牌将于 (UTC) {expiration.strftime("%Y-%m-%d %H:%M:%S")} 过期。')
    click.echo('请妥善保管并在忘记密码页面输入以下令牌：')
    click.echo(raw_token)
    click.echo('=' * 60)
