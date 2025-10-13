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


# --- 通知函数 ---
def send_notification(site_name, url, current_status_key, previous_status, error_detail=None):
    """
    发送企业微信通知的统一函数。

    Args:
        current_status_key (str): 'recovered', 'down', 'slow'
        previous_status (str): 前一个状态的文本描述
    """
    webhook_url = current_app.config.get('QYWECHAT_WEBHOOK_URL')
    if not webhook_url or "YOUR_KEY_HERE" in webhook_url:
        print("企业微信 Webhook URL 未配置，跳过通知。")
        return

    # 根据状态关键字生成通知内容
    if current_status_key == "recovered":
        title = "<font color=\"info\">✅ 网站恢复通知</font>"
        status_text = "已恢复正常"
        color = "info"
    elif current_status_key == "down":
        title = "<font color=\"warning\">🔥 网站访问异常</font>"
        status_text = "无法访问"
        color = "warning"
    elif current_status_key == "slow":
        title = "<font color=\"comment\">⚠️ 网站访问过慢</font>"
        status_text = "访问过慢"
        color = "comment"
    else:
        # 对于 "正常" -> "访问过慢" 这类非关键变更，不发送通知
        return

    content = (
        f"# 网站健康状态变更通知\n\n"
        f"> **网站名称**: {site_name}\n"
        f"> **监控地址**: {url}\n"
        f"> **当前状态**: <font color=\"{color}\">{status_text}</font>\n"
        f"> **上次状态**: {previous_status}"
    )

    if error_detail:
        # 清理和截断错误信息，使其更易读
        clean_error = str(error_detail).replace("'", "`").replace('"', '`')
        content += f"\n> **错误详情**: `{clean_error[:200]}...`"

    payload = {"msgtype": "markdown", "markdown": {"content": content}}

    try:
        requests.post(webhook_url, data=json.dumps(payload), headers={'Content-Type': 'application/json'}, timeout=10)
        print(f"成功发送企业微信通知: {site_name} 状态变更为 {status_text}")
    except Exception as e:
        print(f"发送企业微信通知时发生错误: {e}")


# --- 核心监控逻辑 ---
def _core_check_logic():
    """包含核心检查逻辑的内部函数，以避免代码重复。"""
    sites_to_monitor = MonitoredSite.query.filter_by(is_active=True).all()
    slow_response_threshold = current_app.config.get('SLOW_RESPONSE_THRESHOLD_SECONDS', 5)
    request_timeout = current_app.config.get('REQUEST_TIMEOUT_SECONDS', 10)
    headers = {'User-Agent': 'WebMonitor/1.0'}

    if not sites_to_monitor:
        print("健康检查：数据库中没有活动的监控站点。")
        return

    print(f"开始执行健康检查，共 {len(sites_to_monitor)} 个网站...")

    for site in sites_to_monitor:
        site_name, url = site.name, site.url
        response_time, error_detail, current_status = None, None, None

        try:
            # 1. 执行HTTP请求
            start_time = time.time()
            response = requests.get(url, timeout=request_timeout, headers=headers)
            response_time = time.time() - start_time

            # 2. 分析响应，判断成功状态
            if response.status_code < 400:
                current_status = "访问过慢" if response_time > slow_response_threshold else "正常"

                with status_lock:
                    previous_data = site_statuses.get(site_name, {})
                    # 如果是从“无法访问”的状态中恢复，则发送恢复通知
                    if previous_data.get("status") == "无法访问":
                        send_notification(site_name, url, "recovered", previous_data.get("status"))

                    # 更新状态，并将失败计数器清零
                    site_statuses[site_name] = {
                        "status": current_status,
                        "response_time_seconds": round(response_time, 2),
                        "last_checked": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        "failure_count": 0  # 成功后清零
                    }
            else:
                # 对于非2xx/3xx的响应码，也视为失败
                raise requests.exceptions.RequestException(f"HTTP 状态码: {response.status_code}")

        except requests.exceptions.RequestException as e:
            # 3. 处理所有失败情况（连接超时、HTTP错误等）
            current_status = "无法访问"
            error_detail = str(e)

            with status_lock:
                previous_data = site_statuses.get(site_name, {})
                # 累加失败次数
                new_failure_count = previous_data.get("failure_count", 0) + 1

                # 只有当失败次数达到阈值时，才发送告警
                # 并且只在第一次达到阈值时发送，避免重复告警
                if new_failure_count == FAILURE_CONFIRMATION_THRESHOLD:
                    send_notification(site_name, url, "down", previous_data.get("status", "未知"), error_detail)

                # 更新状态和失败次数
                site_statuses[site_name] = {
                    "status": current_status,
                    "response_time_seconds": None,
                    "last_checked": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "failure_count": new_failure_count
                }

        # 4. 无论成功或失败，都记录日志
        if current_status:
            log_entry = HealthCheckLog(
                site_name=site_name,
                status=current_status,
                response_time_seconds=round(response_time, 2) if response_time else None,
                error_detail = error_detail
            )
            db.session.add(log_entry)

        # 打印本次检查结果
        if response_time is not None:
            print(f"  - {site_name}: {current_status} ({response_time:.2f}s)")
        else:
            print(f"  - {site_name}: {current_status}")

    db.session.commit()
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
