# web-monitor/app/services.py (最终修复版)

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
# 只有当一个站点连续失败达到这个次数时，才发送告警通知
FAILURE_CONFIRMATION_THRESHOLD = 3


# --- 通知函数 (保持不变) ---
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

    if error_detail:
        clean_error = str(error_detail).replace("'", "`").replace('"', '`')
        if http_code:
            content += f"\n> **错误详情**: HTTP {http_code} - `{clean_error[:200]}`"
        else:
            content += f"\n> **错误详情**: `{clean_error[:200]}`"

    payload = {"msgtype": "markdown", "markdown": {"content": content}}

    try:
        requests.post(webhook_url, data=json.dumps(payload), headers={'Content-Type': 'application/json'}, timeout=10)
        print(f"成功发送企业微信通知: {site_name} 状态变更为 {status_text}")
    except Exception as e:
        print(f"发送企业微信通知时发生错误: {e}")


# --- 核心监控逻辑 (彻底重构) ---
def _core_check_logic():
    """包含核心检查逻辑的内部函数。"""
    sites_to_monitor = MonitoredSite.query.filter_by(is_active=True).all()
    if not sites_to_monitor:
        print("健康检查：数据库中没有活动的监控站点。")
        return

    print(f"开始执行健康检查，共 {len(sites_to_monitor)} 个网站...")

    for site in sites_to_monitor:
        site_name, url = site.name, site.url

        # 初始化本次检查的结果变量
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

            # 【核心修复】使用 raise_for_status() 来自动处理 4xx 和 5xx 错误
            # 这会将所有非 2xx 的响应码都抛出 HTTPError 异常
            response.raise_for_status()

            # 如果代码能执行到这里，说明 status_code 是 2xx，请求成功
            if response_time > current_app.config.get('SLOW_RESPONSE_THRESHOLD', 5):
                current_status = '访问过慢'
            else:
                current_status = '正常'

        except requests.exceptions.RequestException as e:
            # 这里会捕获所有 requests 相关的异常，包括连接超时、DNS错误、以及 raise_for_status() 抛出的 HTTPError
            current_status = '无法访问'
            # 尝试从异常中提取更具体的信息
            if isinstance(e, requests.exceptions.HTTPError):
                # 如果是 HTTP 错误，error_detail 就是状态码
                error_detail = f"HTTP {http_status_code}"
            elif isinstance(e, requests.exceptions.Timeout):
                error_detail = "请求超时"
            elif isinstance(e, requests.exceptions.ConnectionError):
                error_detail = "连接错误"
            else:
                error_detail = "未知请求异常"

        # --- 更新全局状态和处理告警 ---
        with status_lock:
            previous_data = site_statuses.get(site_name, {})
            previous_status = previous_data.get("status", "未知")

            # 检查状态是否真的发生了变化
            if current_status != previous_status:
                if current_status in ['正常', '访问过慢']:  # 如果是恢复或变为慢速
                    # 只有从“无法访问”恢复时才发送恢复通知
                    if previous_status == '无法访问' and previous_data.get("notification_sent"):
                        send_notification(site_name, url, "recovered", previous_status)

                    # 更新状态，并将失败计数器和告警标志清零
                    site_statuses[site_name] = {
                        "status": current_status,
                        "failure_count": 0,
                        "notification_sent": False
                    }
                elif current_status == '无法访问':  # 如果是首次变为无法访问
                    site_statuses[site_name] = {
                        "status": current_status,
                        "failure_count": 1,  # 失败计数从1开始
                        "notification_sent": False
                    }
            elif current_status == '无法访问':  # 如果是连续无法访问
                site_statuses[site_name]["failure_count"] += 1

            # 更新通用信息
            site_statuses[site_name]["response_time_seconds"] = round(response_time, 2) if response_time else None
            site_statuses[site_name]["last_checked"] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # --- 独立的告警发送逻辑 ---
            current_data = site_statuses[site_name]
            if (current_data.get("status") == '无法访问' and
                    current_data.get("failure_count") >= FAILURE_CONFIRMATION_THRESHOLD and
                    not current_data.get("notification_sent")):
                send_notification(site_name, url, "down", previous_status, error_detail, http_status_code)
                site_statuses[site_name]["notification_sent"] = True

        # --- 记录日志到数据库 ---
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
