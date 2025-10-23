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

def render_webhook_template(template_text, context):
    """渲染 Webhook 模板"""
    if not template_text:
        return None, '模板内容为空'
    try:
        template = current_app.jinja_env.from_string(template_text)
        return template.render(**context), None
    except Exception as exc:
        return None, str(exc)


def _load_generic_webhook_config():
    """加载通用 Webhook 配置"""
    config = current_app.config
    if not config.get('GENERIC_WEBHOOK_ENABLED'):
        return None
    url = config.get('GENERIC_WEBHOOK_URL')
    template_text = config.get('GENERIC_WEBHOOK_TEMPLATE')
    if not url or not template_text:
        return None
    headers = {}
    config_headers = config.get('GENERIC_WEBHOOK_HEADERS') or {}
    if isinstance(config_headers, dict):
        headers = {str(k): str(v) for k, v in config_headers.items()}
    content_type = config.get('GENERIC_WEBHOOK_CONTENT_TYPE') or 'application/json'
    if content_type and not any(k.lower() == 'content-type' for k in headers):
        headers['Content-Type'] = content_type
    return {
        'url': url,
        'template': template_text,
        'headers': headers,
    }


def send_generic_webhook(event_name, payload):
    """发送通用 Webhook 通知"""
    config = _load_generic_webhook_config()
    if not config:
        return False
    context = dict(payload or {})
    context.setdefault('event', event_name)
    rendered, error = render_webhook_template(config['template'], context)
    if error:
        current_app.logger.warning('[Webhook] 模板渲染失败: %s', error)
        return False
    try:
        response = requests.post(
            config['url'],
            data=rendered.encode('utf-8'),
            headers=config['headers'],
            timeout=10
        )
        if 200 <= response.status_code < 300:
            current_app.logger.info('[Webhook] 通知已发送: %s', event_name)
            return True
        current_app.logger.warning(
            '[Webhook] 通知发送失败，状态码 %s，响应: %s',
            response.status_code,
            response.text[:200]
        )
    except Exception as exc:
        current_app.logger.exception('[Webhook] 通知请求异常: %s', exc)
    return False


def _send_wechat_markdown(content, *, webhook_url, log_prefix, success_context):
    """发送企业微信 Markdown 通知"""
    if not webhook_url or "YOUR_KEY_HERE" in webhook_url:
        print(f"{log_prefix} 企业微信 Webhook URL 未配置，跳过通知。")
        return False
    payload = {"msgtype": "markdown", "markdown": {"content": content}}
    try:
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
            print(f"{log_prefix} 企业微信通知发送成功: {success_context}")
        else:
            print(f"{log_prefix} 企业微信通知发送失败: {success_context}，原因: {err_detail_msg}")
        return ok
    except Exception as exc:
        print(f"{log_prefix} 发送企业微信通知时发生异常: {exc}")
        return False


def send_notification(site_name, url, current_status_key, previous_status, *, error_detail=None, http_code=None,
                      context=None):
    """
    发送企业微信通知和通用 Webhook 的统一函数。
    current_status_key: "down" | "recovered" | "slow" | "slow_recovered"
    previous_status: 通知中用于显示的上次状态（字符串）
    context: 可选的 (label, value) 元组列表，用于拼接额外字段
    """
    webhook_url = current_app.config.get('QYWECHAT_WEBHOOK_URL')

    status_map = {
        "down": ("网站宕机告警通知", "无法访问", "warning"),
        "recovered": ("网站恢复通知", "已恢复正常", "info"),
        "slow": ("网站性能告警通知", "访问过慢", "comment"),
        "slow_recovered": ("网站性能恢复通知", "访问速度恢复正常", "info"),
    }
    status_meta = status_map.get(current_status_key)
    if not status_meta:
        return
    title, status_text, color = status_meta
    # 1. 发送企业微信通知
    if webhook_url and "YOUR_KEY_HERE" not in webhook_url:
        content = (
            f"## {title}\n"
            f"> **网站名称**: {site_name}\n"
            f"> **监控地址**: {url}\n"
            f"> **当前状态**: <font color=\"{color}\">{status_text}</font>\n"
            f"> **上次状态**: {previous_status}"
        )
        if context:
            for label, value in context:
                if value is None or value == "":
                    continue
                content += f"\n> **{label}**: {value}"
        if error_detail:
            reason = str(error_detail).replace("'", "`").replace('"', '`')
            if http_code and http_code >= 400:
                reason = f"HTTP {http_code}"
            content += f"\n> **错误详情**: `{reason}`"
        elif http_code and http_code >= 400:
            content += f"\n> **错误详情**: `HTTP {http_code}`"
        print(f"[通知] 准备发送企业微信通知: {site_name} - {status_text} -> 上次状态: {previous_status} | URL: {url}")
        _send_wechat_markdown(
            content,
            webhook_url=webhook_url,
            log_prefix='[通知]',
            success_context=f"{site_name} 状态变更为 {status_text}"
        )
    # 2. 发送通用 Webhook 通知
    webhook_payload = {
        'event_title': title,
        'site_name': site_name,
        'site_url': url,
        'status_key': current_status_key,
        'status_label': status_text,
        'previous_status': previous_status,
        'severity': 'warning' if current_status_key in ['down', 'slow'] else 'info',
        'timestamp': datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        'http_code': http_code,
        'error_detail': error_detail,
        'details': [{'label': str(label), 'value': value} for label, value in (context or [])]
    }
    send_generic_webhook('site_status_change', webhook_payload)


def send_management_notification(event_title, *, operator=None, details=None):
    """发送后台配置变更的企业微信通知和通用 Webhook。"""
    webhook_url = current_app.config.get('QYWECHAT_WEBHOOK_URL')
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 1. 企业微信通知
    if webhook_url and "YOUR_KEY_HERE" not in webhook_url:
        content = (
            f"## 配置变更通知\n"
            f"> **事件**: {event_title}\n"
            f"> **发生时间**: {timestamp}"
        )
        if operator:
            content += f"\n> **操作人**: {operator}"
        if details:
            for label, value in details:
                if value is None or value == "":
                    continue
                content += f"\n> **{label}**: {value}"
        print(f"[配置通知] 准备发送企业微信通知: {event_title}")
        _send_wechat_markdown(
            content,
            webhook_url=webhook_url,
            log_prefix='[配置通知]',
            success_context=event_title
        )
    # 2. 通用 Webhook 通知
    webhook_payload = {
        'event_title': event_title,
        'operator': operator or '系统',
        'timestamp': timestamp,
        'details': [{'label': str(label), 'value': value} for label, value in (details or [])]
    }
    send_generic_webhook('management_config_change', webhook_payload)


# --- 内部工具函数 ---
def _parse_datetime_safe(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _format_duration(delta):
    if not delta:
        return None
    seconds = int(delta.total_seconds())
    if seconds < 0:
        seconds = 0
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}天")
    if hours:
        parts.append(f"{hours}小时")
    if minutes:
        parts.append(f"{minutes}分钟")
    if seconds or not parts:
        parts.append(f"{seconds}秒")
    return ''.join(parts)


def _format_ratio(count, total):
    return f"{count}/-" if not total else f"{count}/{total}"


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
    fail_consecutive = current_app.config.get('FAILURE_CONFIRMATION_THRESHOLD', 3)
    window_size = current_app.config.get('FAILURE_WINDOW_SIZE', 5)
    window_threshold = current_app.config.get('FAILURE_WINDOW_THRESHOLD', 3)
    recovery_consecutive = current_app.config.get('RECOVERY_CONFIRMATION_THRESHOLD', 2)
    quick_retry_count = current_app.config.get('QUICK_RETRY_COUNT', 1)
    quick_retry_delay = current_app.config.get('QUICK_RETRY_DELAY_SECONDS', 2)
    slow_consecutive = current_app.config.get('SLOW_RESPONSE_CONFIRMATION_THRESHOLD', 3)
    slow_window_size = current_app.config.get('SLOW_RESPONSE_WINDOW_SIZE', 5)
    slow_window_threshold = current_app.config.get('SLOW_RESPONSE_WINDOW_THRESHOLD', 3)
    slow_recovery_consecutive = current_app.config.get('SLOW_RESPONSE_RECOVERY_THRESHOLD', recovery_consecutive)

    print(f"开始执行健康检查，共 {len(sites_to_monitor)} 个网站...")

    for site in sites_to_monitor:
        site_name, url = site.name, site.url

        current_status = "未知"
        response_time = None
        http_status_code = None
        error_detail = None

        try:
            current_status, response_time, http_status_code, _ = _single_http_check(url, request_timeout, slow_threshold)
        except requests.exceptions.RequestException as e:
            current_status = '无法访问'
            if isinstance(e, requests.exceptions.HTTPError):
                error_detail = "服务器错误"
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

            retry_succeeded = False
            for _ in range(quick_retry_count):
                try:
                    time.sleep(quick_retry_delay)
                    current_status, response_time, http_status_code, _ = _single_http_check(
                        url, request_timeout, slow_threshold
                    )
                    retry_succeeded = True
                    break
                except requests.exceptions.RequestException:
                    continue
            if retry_succeeded:
                error_detail = None

        now = datetime.datetime.now()
        now_str = now.strftime('%Y-%m-%d %H:%M:%S')
        rounded_response_time = round(response_time, 2) if response_time is not None else None
        response_time_display = f"{rounded_response_time:.2f}秒" if rounded_response_time is not None else None

        with status_lock:
            prev = site_statuses.get(site_name, {})
            prev_status = prev.get("status", "未知")
            notification_sent = prev.get("notification_sent", False)
            slow_notification_sent = prev.get("slow_notification_sent", False)
            prev_failure_count = prev.get("failure_count", 0)
            prev_success_count = prev.get("success_count", 0)
            prev_slow_count = prev.get("slow_count", 0)
            prev_history = prev.get("history", [])
            prev_slow_history = prev.get("slow_history", [])
            prev_total_checks = prev.get("total_checks", 0)
            prev_down_since_dt = _parse_datetime_safe(prev.get("down_since"))
            prev_slow_since_dt = _parse_datetime_safe(prev.get("slow_since"))

            total_checks = prev_total_checks + 1
            is_down = current_status == '无法访问'
            is_slow = current_status == '访问过慢'

            down_since_dt = prev_down_since_dt
            slow_since_dt = prev_slow_since_dt

            if is_down:
                failure_count = prev_failure_count + 1 if prev_status == '无法访问' else 1
                success_count = 0
                slow_count = 0
                slow_history = (prev_slow_history + [0])[-slow_window_size:] if slow_window_size > 0 else []
                slow_notification_sent = False
                slow_since_dt = None
                if prev_status != '无法访问':
                    down_since_dt = now
            else:
                failure_count = 0
                slow_history = (prev_slow_history + [1 if is_slow else 0])[-slow_window_size:] if slow_window_size > 0 else []
                if is_slow:
                    slow_count = prev_slow_count + 1 if prev_status == '访问过慢' else 1
                    if prev_status != '访问过慢':
                        slow_since_dt = now
                else:
                    slow_count = 0
                    slow_since_dt = None
                if current_status == '正常':
                    success_count = prev_success_count + 1 if prev_status == '正常' else 1
                else:
                    success_count = 0
                down_since_dt = None

            history = (prev_history + [1 if is_down else 0])[-window_size:] if window_size > 0 else []
            fails_in_window = sum(history)
            slows_in_window = sum(slow_history)

            down_since_str = down_since_dt.strftime('%Y-%m-%d %H:%M:%S') if down_since_dt else None
            slow_since_str = slow_since_dt.strftime('%Y-%m-%d %H:%M:%S') if slow_since_dt else None
            failure_window_display = _format_ratio(fails_in_window, len(history) or window_size)
            slow_window_display = _format_ratio(slows_in_window, len(slow_history) or slow_window_size)

            site_statuses[site_name] = {
                "status": current_status,
                "failure_count": failure_count,
                "success_count": success_count,
                "slow_count": slow_count,
                "history": history,
                "slow_history": slow_history,
                "notification_sent": notification_sent,
                "slow_notification_sent": slow_notification_sent,
                "response_time_seconds": rounded_response_time,
                "last_checked": now_str,
                "down_since": down_since_str,
                "slow_since": slow_since_str,
                "total_checks": total_checks
            }

            down_duration_str = _format_duration(now - down_since_dt) if down_since_dt else None
            slow_duration_str = _format_duration(now - slow_since_dt) if slow_since_dt else None

            if is_down and not notification_sent:
                if failure_count >= fail_consecutive or fails_in_window >= window_threshold:
                    print(
                        f"[告警触发] 宕机: {site_name} 当前状态={current_status}, 上次状态={prev_status}, "
                        f"连续失败={failure_count}, 窗口失败={failure_window_display}, HTTP={http_status_code or 'N/A'}, "
                        f"错误={error_detail or 'N/A'}, 故障开始={down_since_str or '刚刚'}"
                    )
                    context = [
                        ("检测时间", now_str),
                        ("故障开始时间", down_since_str or now_str),
                        ("已持续", down_duration_str or "0秒"),
                        ("连续失败次数", failure_count),
                        ("窗口失败次数", failure_window_display),
                        ("累计检查次数", total_checks),
                    ]
                    send_notification(
                        site_name,
                        url,
                        "down",
                        prev_status,
                        error_detail=error_detail,
                        http_code=http_status_code,
                        context=context
                    )
                    site_statuses[site_name]["notification_sent"] = True

            if site_statuses[site_name]["notification_sent"] and current_status == '正常':
                if success_count >= recovery_consecutive:
                    recovery_duration = _format_duration(now - prev_down_since_dt) if prev_down_since_dt else None
                    recovery_context = [
                        ("恢复检测时间", now_str),
                        ("故障持续时长", recovery_duration),
                        ("累计检查次数", total_checks),
                        ("最近一次响应时间", response_time_display),
                    ]
                    print(
                        f"[告警触发] 恢复: {site_name} 当前状态={current_status}, 上次状态=无法访问, "
                        f"连续正常={success_count}, 持续时长={recovery_duration or '未知'}"
                    )
                    send_notification(
                        site_name,
                        url,
                        "recovered",
                        "无法访问",
                        context=recovery_context
                    )
                    site_statuses[site_name]["notification_sent"] = False

            if is_slow and not is_down and not site_statuses[site_name]["slow_notification_sent"]:
                if slow_count >= slow_consecutive or slows_in_window >= slow_window_threshold:
                    print(
                        f"[告警触发] 慢响应: {site_name} 响应时间={response_time_display or 'N/A'}, "
                        f"连续慢响应={slow_count}, 窗口慢响应={slow_window_display}"
                    )
                    slow_context = [
                        ("检测时间", now_str),
                        ("访问减速开始时间", slow_since_str or now_str),
                        ("已持续", slow_duration_str or "0秒"),
                        ("连续慢响应次数", slow_count),
                        ("窗口慢响应次数", slow_window_display),
                        ("最近一次响应时间", response_time_display),
                        ("累计检查次数", total_checks),
                    ]
                    send_notification(
                        site_name,
                        url,
                        "slow",
                        prev_status,
                        error_detail=error_detail,
                        http_code=http_status_code,
                        context=slow_context
                    )
                    site_statuses[site_name]["slow_notification_sent"] = True

            if site_statuses[site_name]["slow_notification_sent"] and current_status == '正常':
                if success_count >= slow_recovery_consecutive:
                    slow_recovery_duration = _format_duration(now - prev_slow_since_dt) if prev_slow_since_dt else None
                    slow_recovery_context = [
                        ("恢复检测时间", now_str),
                        ("慢响应持续时长", slow_recovery_duration),
                        ("累计检查次数", total_checks),
                        ("最近一次响应时间", response_time_display),
                    ]
                    print(
                        f"[告警触发] 慢响应恢复: {site_name} 当前状态={current_status}, "
                        f"连续正常={success_count}, 慢响应持续时长={slow_recovery_duration or '未知'}"
                    )
                    send_notification(
                        site_name,
                        url,
                        "slow_recovered",
                        "访问过慢",
                        context=slow_recovery_context
                    )
                    site_statuses[site_name]["slow_notification_sent"] = False

        log_entry = HealthCheckLog(
            site_name=site_name,
            status=current_status,
            response_time_seconds=rounded_response_time,
            http_status_code=http_status_code,
            error_detail=error_detail
        )
        db.session.add(log_entry)

        print(
            f"  - {site_name}: {current_status} (HTTP {http_status_code or 'N/A'}), "
            f"响应时间: {response_time_display or 'N/A'}, 连续失败: {failure_count}, 窗口失败: {failure_window_display}, "
            f"连续慢响应: {slow_count}, 慢响应窗口: {slow_window_display}, 连续正常: {success_count}, 累计检查: {total_checks}"
        )

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"健康检查日志提交失败: {e}")
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
