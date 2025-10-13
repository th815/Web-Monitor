import requests
import json
import time
import datetime
import threading
from flask import current_app
from .extensions import db
from .models import HealthCheckLog, MonitoredSite

site_statuses = {}
status_lock = threading.Lock()
def send_wechat_notification(site_name, url, status, previous_status, response_time=None, error_message=None):
    """发送企业微信通知"""
    webhook_url = current_app.config.get('QYWECHAT_WEBHOOK_URL')
    if not webhook_url or "YOUR_KEY_HERE" in webhook_url:
        print("企业微信 Webhook URL 未配置，跳过通知。")
        return
    if status == "恢复访问":
        title, status_color, status_text = f"<font color=\"info\">✅ 网站恢复通知</font>", "info", "已恢复访问"
    elif status == "无法访问":
        title, status_color, status_text = f"<font color=\"warning\">🔥 网站访问异常</font>", "warning", "无法访问"
    elif status == "访问过慢":
        title, status_color, status_text = f"<font color=\"comment\">⚠️ 网站访问过慢</font>", "comment", f"访问过慢 ({response_time:.2f}秒)"
    else:
        return
    content = f"# 网站健康状态变更通知\n\n> **网站名称**: {site_name}\n> **监控地址**: {url}\n> **当前状态**: <font color=\"{status_color}\">{status_text}</font>\n> **上次状态**: {previous_status}"
    if error_message:
        content += f"\n> **错误详情**: {error_message}"
    payload = {"msgtype": "markdown", "markdown": {"content": content}}
    try:
        requests.post(webhook_url, data=json.dumps(payload), headers={'Content-Type': 'application/json'}, timeout=10)
        print(f"成功发送企业微信通知: {site_name} 状态变更为 {status}")
    except Exception as e:
        print(f"发送企业微信通知时发生错误: {e}")
def _core_check_logic():
    """包含核心检查逻辑的内部函数，以避免代码重复。"""
    sites_to_monitor_objects = MonitoredSite.query.filter_by(is_active=True).all()
    sites_to_monitor = [site.to_dict() for site in sites_to_monitor_objects]
    slow_response_threshold = current_app.config['SLOW_RESPONSE_THRESHOLD_SECONDS']

    if not sites_to_monitor:
        print("健康检查：数据库中没有活动的监控站点。")
        return

    print(f"开始执行健康检查，共 {len(sites_to_monitor)} 个网站...")
    for site in sites_to_monitor:
        site_name, url = site["name"], site["url"]
        current_status, response_time, error_message = "未知", None, None

        try:
            start_time = time.time()
            response = requests.get(url, timeout=10)
            response_time = time.time() - start_time

            if 200 <= response.status_code < 400:
                current_status = "访问过慢" if response_time > slow_response_threshold else "正常"
            else:
                current_status, error_message = "无法访问", f"HTTP状态码: {response.status_code}"

        except requests.exceptions.RequestException as e:
            current_status, error_message = "无法访问", str(e)

        with status_lock:
            # ... (这部分逻辑和之前完全一样)
            previous_status = site_statuses.get(site_name, {}).get("status", "未知")
            if previous_status in ["无法访问", "访问过慢"] and current_status == "正常":
                send_wechat_notification(site_name, url, "恢复访问", previous_status)
            elif current_status != previous_status and current_status != "正常":
                send_wechat_notification(site_name, url, current_status, previous_status, response_time, error_message)
            site_statuses[site_name] = {
                "url": url, "status": current_status,
                "response_time_seconds": round(response_time, 2) if response_time else None,
                "last_checked": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "error_message": error_message
            }
            log_entry = HealthCheckLog(site_name=site_name, status=current_status, response_time_seconds=response_time)
            db.session.add(log_entry)
            db.session.commit()

        print(
            f"  - {site_name}: {current_status} ({response_time:.2f}s)" if response_time is not None else f"  - {site_name}: {current_status}")

    print("健康检查完成。")


def check_website_health(app=None):
    """
    健康检查的入口函数。
    如果 app 参数被提供 (来自 APScheduler)，则手动推入上下文。
    否则 (来自首次执行)，假定已在上下文中。
    """
    if app:
        with app.app_context():
            _core_check_logic()
    else:
        _core_check_logic()


def cleanup_old_data(app=None):
    """
    清理数据的入口函数，逻辑同上。
    """
    def _core_cleanup_logic():
        retention_days = current_app.config['DATA_RETENTION_DAYS']
        cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=retention_days)
        deleted_count = db.session.query(HealthCheckLog).filter(HealthCheckLog.timestamp < cutoff_date).delete()
        db.session.commit()
        if deleted_count > 0:
            print(f"数据库清理任务：已清理 {deleted_count} 条 {retention_days} 天前的旧数据。")
        else:
            print("数据库清理任务：没有需要清理的旧数据。")

    if app:
        with app.app_context():
            _core_cleanup_logic()
    else:
        _core_cleanup_logic()

