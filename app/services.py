# web-monitor/app/services.py (改进版 v3: 提升告警准确性，避免抖动/漏报)
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


# --- 通知函数 ---
def send_notification(site_name, url, current_status_key, previous_status, error_detail=None, http_code=None):
    """
    发送企业微信通知的统一函数。
    current_status_key: "down" | "recovered"
    previous_status: 通知中用于显示的上次状态（字符串）
    """
    webhook_url = current_app.config.get('QYWECHAT_WEBHOOK_URL')
    if not webhook_url or "YOUR_KEY_HERE" in webhook_url:
        print("企业微信 Webhook URL 未配置，跳过通知。")
        return

    if current_status_key == "recovered":
        status_text = "已恢复正常"
        color = "info"
    elif current_status_key == "down":
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

    # 构建更详细的错误原因，优先显示 HTTP Code
    if error_detail:
        reason = str(error_detail).replace("'", "`").replace('"', '`')
        if http_code and http_code >= 400:
            reason = f"HTTP {http_code}"
        content += f"\n> **错误详情**: `{reason}`"

    payload = {"msgtype": "markdown", "markdown": {"content": content}}
    try:
        print(f"[通知] 准备发送企业微信通知: {site_name} - {status_text} -> 上次状态: {previous_status} | URL: {url}")
        resp = requests.post(
            webhook_url,
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        ok = False
        err_detail_msg = ""
        if resp.status_code == 200:
            try:
                res_json = resp.json()
            except ValueError:
                res_json = None
            if isinstance(res_json, dict) and res_json.get("errcode") == 0:
                ok = True
            else:
                err_detail_msg = f"非零返回: {res_json}"
        else:
            err_detail_msg = f"HTTP {resp.status_code}, body: {resp.text[:200]}"
        if ok:
            print(f"[通知] 企业微信通知发送成功: {site_name} 状态变更为 {status_text}")
        else:
            print(f"[通知] 企业微信通知发送失败: {site_name} 状态变更为 {status_text}，原因: {err_detail_msg}")
    except Exception as e:
        print(f"[通知] 发送企业微信通知时发生异常: {e}")


# --- 内部工具函数 ---
def _single_http_check(url, timeout, slow_threshold):
    """执行一次 HTTP 检查，返回 (status, response_time, http_code, error_detail)。
    status: '正常' | '访问过慢' | 抛异常
    """
    start_time = time.time()
    response = requests.get(
        url,
        timeout=timeout,
        headers={'User-Agent': 'WebMonitor/1.0'}
    )
    response_time = time.time() - start_time
    http_status_code = response.status_code
    response.raise_for_status()
    if response_time > slow_threshold:
        return '访问过慢', response_time, http_status_code, None
    return '正常', response_time, http_status_code, None


# --- 核心监控逻辑 ---
def _core_check_logic():
    """包含核心检查逻辑的内部函数。"""
    sites_to_monitor = MonitoredSite.query.filter_by(is_active=True).all()
    if not sites_to_monitor:
        print("健康检查：数据库中没有活动的监控站点。")
        return

    # 读取配置与默认值
    request_timeout = current_app.config.get('REQUEST_TIMEOUT', 10)
    slow_threshold = current_app.config.get('SLOW_RESPONSE_THRESHOLD_SECONDS',
                                            current_app.config.get('SLOW_RESPONSE_THRESHOLD', 5))
    # 连续失败阈值（防止误报）
    fail_consecutive = current_app.config.get('FAILURE_CONFIRMATION_THRESHOLD', 3)
    # 滑动窗口判定（提升短时故障捕捉能力，同时抑制抖动）
    window_size = current_app.config.get('FAILURE_WINDOW_SIZE', 5)
    window_threshold = current_app.config.get('FAILURE_WINDOW_THRESHOLD', 3)  # 最近 window_size 次中失败 >= 该值 则告警
    # 恢复需要连续成功次数阈值（避免快速抖动导致的假恢复）
    recovery_consecutive = current_app.config.get('RECOVERY_CONFIRMATION_THRESHOLD', 2)
    # 失败时快速复检（降低网络瞬断误报）
    quick_retry_count = current_app.config.get('QUICK_RETRY_COUNT', 1)
    quick_retry_delay = current_app.config.get('QUICK_RETRY_DELAY_SECONDS', 2)

    print(f"开始执行健康检查，共 {len(sites_to_monitor)} 个网站...")

    for site in sites_to_monitor:
        site_name, url = site.name, site.url

        current_status = "未知"
        response_time = None
        http_status_code = None
        error_detail = None

        # 1) 首次请求
        try:
            current_status, response_time, http_status_code, _ = _single_http_check(url, request_timeout, slow_threshold)
        except requests.exceptions.RequestException as e:
            current_status = '无法访问'
            if isinstance(e, requests.exceptions.HTTPError):
                error_detail = "服务器错误"  # 具体 code 通过 http_status_code 单独记录
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        http_status_code = e.response.status_code
                    except Exception:
                        http_status_code = None
            elif isinstance(e, requests.exceptions.Timeout):
                error_detail = "请求超时"
            elif isinstance(e, requests.exceptions.ConnectionError):
                error_detail = "连接错误"
            else:
                error_detail = "未知请求异常"

            # 2) 快速重试，尽量避免瞬时网络抖动导致误报
            retry_succeeded = False
            for _ in range(quick_retry_count):
                try:
                    time.sleep(quick_retry_delay)
                    current_status, response_time, http_status_code, _ = _single_http_check(
                        url, request_timeout, slow_threshold
                    )
                    retry_succeeded = True
                    # 成功就结束重试
                    break
                except requests.exceptions.RequestException:
                    continue
            if retry_succeeded:
                # 重试成功视为本次检查成功，清空错误详情
                error_detail = None
            else:
                # 仍然失败则维持 "无法访问" 的结论
                pass

        # 3) 更新状态与判定告警/恢复
        with status_lock:
            prev = site_statuses.get(site_name, {})
            prev_status = prev.get("status", "未知")
            notification_sent = prev.get("notification_sent", False)
            failure_count = prev.get("failure_count", 0)
            success_count = prev.get("success_count", 0)
            history = prev.get("history", [])  # 仅存 0/1 序列（0=成功，1=失败）

            is_down = (current_status == '无法访问')

            # 滑动窗口历史
            history = (history + [1 if is_down else 0])[-window_size:]
            fails_in_window = sum(history)

            # 连续计数
            if is_down:
                failure_count = failure_count + 1 if prev_status == '无法访问' else 1
                success_count = 0
            else:
                success_count = success_count + 1 if prev_status in ['正常', '访问过慢'] else 1
                failure_count = 0

            # 保存最新状态
            site_statuses[site_name] = {
                "status": current_status,
                "failure_count": failure_count,
                "success_count": success_count,
                "history": history,
                "notification_sent": notification_sent,
                "response_time_seconds": round(response_time, 2) if response_time else None,
                "last_checked": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

            # 触发宕机告警（满足 连续失败 或 窗口失败 比例）且尚未告警
            if is_down and not notification_sent:
                if failure_count >= fail_consecutive or fails_in_window >= window_threshold:
                    print(f"[告警触发] 宕机: {site_name} 当前状态={current_status}, 上次状态={prev_status}, 连续失败={failure_count}, 窗口失败={fails_in_window}/{len(history)}, HTTP={http_status_code or 'N/A'}, 错误={error_detail or 'N/A'}")
                    send_notification(site_name, url, "down", prev_status, error_detail, http_status_code)
                    site_statuses[site_name]["notification_sent"] = True

            # 触发恢复通知（需要足够的连续成功，避免抖动）
            if (not is_down) and notification_sent:
                if success_count >= recovery_consecutive:
                    print(f"[告警触发] 恢复: {site_name} 当前状态={current_status}, 上次状态=无法访问, 连续成功={success_count}")
                    # 恢复的“上次状态”统一显示为 "无法访问"，更符合语义
                    send_notification(site_name, url, "recovered", "无法访问")
                    site_statuses[site_name]["notification_sent"] = False

        # 4) 记录日志到数据库
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
            f"  - {site_name}: {current_status} (HTTP {http_status_code or 'N/A'}), "
            f"连续失败: {failure_count}, 窗口失败: {fails_in_window}/{len(history)}, 连续成功: {success_count}"
        )

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
