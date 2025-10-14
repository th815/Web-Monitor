# web-monitor/app/services.py (最终修复版 v2)
import requests
import json
import time
import datetime
import threading
from flask import current_app
from .extensions import db
from .models import HealthCheckLog, MonitoredSite

# --- 全局状态变量 ---
site_statuses = {}
status_lock = threading.Lock()
# --- 配置常量 ---
FAILURE_CONFIRMATION_THRESHOLD = 3


# --- 通知函数 (最终版) ---
def send_notification(site_name, url, current_status_key, previous_status, error_detail=None, http_code=None):
    """
    发送企业微信通知的统一函数。
    """
    webhook_url = current_app.config.get('QYWECHAT_WEBHOOK_URL')
    if not webhook_url or "YOUR_KEY_HERE" in webhook_url:
        print("企业微信 Webhook URL 未配置，跳过通知。")
        return
    if current_status_key == "recovered":
        title = "<font color=\"info\">✅ 网站恢复通知</font>"
        status_text = "已恢复正常"
        color = "info"
    elif current_status_key == "down":
        title = "<font color=\"warning\">🔥 网站访问异常</font>"
        status_text = "无法访问"
        color = "warning"
    else:
        return
    content = (
        f"## 网站健康状态变更通知\n"
        f"> **网站名称**: {site_name}\n"
        f"> **监控地址**: {url}\n"
        f"> **当前状态**: <font color=\"{color}\">{status_text}</font>\n"
        f"> **上次状态**: {previous_status}"
    )
    # 【核心修改】构建更详细的错误原因，优先显示 HTTP Code
    if error_detail:
        reason = str(error_detail).replace("'", "`").replace('"', '`')
        # 如果有 HTTP Code，就用它来覆盖或补充 reason
        if http_code and http_code >= 400:
            reason = f"HTTP {http_code}"

        content += f"\n> **错误详情**: `{reason}`"
    payload = {"msgtype": "markdown", "markdown": {"content": content}}
    try:
        requests.post(webhook_url, data=json.dumps(payload), headers={'Content-Type': 'application/json'}, timeout=10)
        print(f"成功发送企业微信通知: {site_name} 状态变更为 {status_text}")
    except Exception as e:
        print(f"发送企业微信通知时发生错误: {e}")


# --- 核心监控逻辑 (最终版) ---
def _core_check_logic():
    """包含核心检查逻辑的内部函数。"""
    sites_to_monitor = MonitoredSite.query.filter_by(is_active=True).all()
    if not sites_to_monitor:
        print("健康检查：数据库中没有活动的监控站点。")
        return
    print(f"开始执行健康检查，共 {len(sites_to_monitor)} 个网站...")
    for site in sites_to_monitor:
        site_name, url = site.name, site.url

        current_status = "未知"
        response_time = None
        http_status_code = None
        error_detail = None
        try:
            start_time = time.time()
            response = requests.get(
                url,
                timeout=current_app.config.get('REQUEST_TIMEOUT', 10),
                headers={'User-Agent': 'WebMonitor/1.0'}
            )
            response_time = time.time() - start_time
            http_status_code = response.status_code
            response.raise_for_status()
            if response_time > current_app.config.get('SLOW_RESPONSE_THRESHOLD', 5):
                current_status = '访问过慢'
            else:
                current_status = '正常'
        except requests.exceptions.RequestException as e:
            current_status = '无法访问'
            if isinstance(e, requests.exceptions.HTTPError):
                error_detail = f"服务器错误"  # 简化，因为code会单独传递
            elif isinstance(e, requests.exceptions.Timeout):
                error_detail = "请求超时"
            elif isinstance(e, requests.exceptions.ConnectionError):
                error_detail = "连接错误"
            else:
                error_detail = "未知请求异常"

        with status_lock:
            previous_data = site_statuses.get(site_name, {})
            previous_status = previous_data.get("status", "未知")

            if current_status != previous_status:
                if current_status in ['正常', '访问过慢']:
                    if previous_status == '无法访问' and previous_data.get("notification_sent"):
                        send_notification(site_name, url, "recovered", previous_status)

                    site_statuses[site_name] = {
                        "status": current_status,
                        "failure_count": 0,
                        "notification_sent": False
                    }
                elif current_status == '无法访问':
                    site_statuses[site_name] = {
                        "status": current_status,
                        "failure_count": 1,
                        "notification_sent": False
                    }
            elif current_status == '无法访问':
                site_statuses[site_name]["failure_count"] += 1
            site_statuses[site_name]["response_time_seconds"] = round(response_time, 2) if response_time else None
            site_statuses[site_name]["last_checked"] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            current_data = site_statuses[site_name]
            if (current_data.get("status") == '无法访问' and
                    current_data.get("failure_count") >= FAILURE_CONFIRMATION_THRESHOLD and
                    not current_data.get("notification_sent")):
                # 【核心修改】将 http_status_code 传递给通知函数
                send_notification(site_name, url, "down", previous_status, error_detail, http_status_code)
                site_statuses[site_name]["notification_sent"] = True
        log_entry = HealthCheckLog(
            site_name=site_name,
            status=current_status,
            response_time_seconds=round(response_time, 2) if response_time else None,
            http_status_code=http_status_code,
            error_detail=error_detail
        )
        db.session.add(log_entry)
        db.session.commit()
        print(
            f"  - {site_name}: {current_status} (HTTP {http_status_code or 'N/A'}), 失败计数: {site_statuses.get(site_name, {}).get('failure_count', 0)}")
    print("健康检查完成。")


# --- 调度器入口函数 ---

def check_website_health(app=None):
    """健康检查的入口函数，负责处理应用上下文。"""
    if app:
        with app.app_context():
            _core_check_logic()
    else:
        # 假设已在上下文中（例如，从 `flask shell` 或首次运行时调用）
        _core_check_logic()


def cleanup_old_data(app=None):
    """清理旧数据的入口函数，负责处理应用上下文。"""

    def _core_cleanup_logic():
        retention_days = current_app.config['DATA_RETENTION_DAYS']
        cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=retention_days)

        try:
            deleted_count = db.session.query(HealthCheckLog).filter(HealthCheckLog.timestamp < cutoff_date).delete(
                synchronize_session=False)
            db.session.commit()
            if deleted_count > 0:
                print(f"数据库清理任务：已清理 {deleted_count} 条 {retention_days} 天前的旧数据。")
            else:
                print("数据库清理任务：没有需要清理的旧数据。")
        except Exception as e:
            db.session.rollback()
            print(f"数据库清理任务失败: {e}")

    if app:
        with app.app_context():
            _core_cleanup_logic()
    else:
        _core_cleanup_logic()
