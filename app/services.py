# web-monitor/app/services.py (改进版 v3: 提升告警准确性，避免抖动/漏报)
import requests
import json
import time
import datetime
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterable, List, Optional, Tuple

from flask import current_app
from .extensions import db
from .models import HealthCheckLog, MonitoredSite, NotificationChannel
from .utils import to_gmt8

# --- 全局状态变量 ---
site_statuses = {}
status_lock = threading.Lock()


# --- 服务启动时的状态初始化函数 ---
def initialize_site_statuses(app):
    """
    在服务启动时从数据库恢复站点的最新状态，预热 site_statuses 字典。
    """
    with app.app_context():
        print("正在从数据库初始化站点状态...")
        try:
            active_sites = MonitoredSite.query.filter_by(is_active=True).all()
            site_names = [site.name for site in active_sites]
            if not site_names:
                print("没有活动的监控站点，初始化完成。")
                return
            # 使用 SQL 子查询找到每个站点的最新日志记录
            from sqlalchemy import func
            subquery = db.session.query(
                HealthCheckLog.site_name,
                func.max(HealthCheckLog.timestamp).label('max_timestamp')
            ).filter(HealthCheckLog.site_name.in_(site_names)).group_by(HealthCheckLog.site_name).subquery()
            latest_logs = db.session.query(HealthCheckLog).join(
                subquery,
                db.and_(
                    HealthCheckLog.site_name == subquery.c.site_name,
                    HealthCheckLog.timestamp == subquery.c.max_timestamp
                )
            ).all()
            with status_lock:
                for site in active_sites:
                    # 为每个站点设置一个默认的未知状态
                    site_statuses[site.name] = {
                        "status": "未知",
                        "last_checked": "N/A",
                        "response_time_seconds": None,
                        "total_checks": 0,
                        # ... 其他字段的默认值 ...
                        "failure_count": 0,
                        "success_count": 0,
                        "slow_count": 0,
                        "history": [],
                        "slow_history": [],
                        "notification_sent": False,
                        "slow_notification_sent": False,
                        "down_since": None,
                        "slow_since": None,
                        "last_notifications": {},
                    }

                # 用数据库中的最新日志更新状态
                for log in latest_logs:
                    if log.site_name in site_statuses:
                        site_statuses[log.site_name].update({
                            "status": log.status,
                            "last_checked": to_gmt8(log.timestamp).strftime(
                                '%Y-%m-%d %H:%M:%S') if log.timestamp else 'N/A',
                            "response_time_seconds": log.response_time_seconds,
                        })

            print(f"成功初始化 {len(latest_logs)} 个站点的状态。")
        except Exception as e:
            print(f"初始化站点状态失败: {e}")


# --- 通知函数 ---

SITE_EVENT_META = {
    'down': {
        'title': '网站宕机告警通知',
        'status_label': '无法访问',
        'status_color': 'warning',
        'severity': 'warning',
    },
    'recovered': {
        'title': '网站恢复通知',
        'status_label': '已恢复正常',
        'status_color': 'info',
        'severity': 'info',
    },
    'slow': {
        'title': '网站性能告警通知',
        'status_label': '访问过慢',
        'status_color': 'comment',
        'severity': 'warning',
    },
    'slow_recovered': {
        'title': '网站性能恢复通知',
        'status_label': '访问速度恢复正常',
        'status_color': 'info',
        'severity': 'info',
    },
}

CHANNEL_REQUEST_TIMEOUT = 10
DEFAULT_NOTIFICATION_WORKERS = 4


def render_webhook_template(template_text, context):
    """渲染 Webhook 模板"""
    if not template_text:
        return None, '模板内容为空'
    try:
        template = current_app.jinja_env.from_string(template_text)
        return template.render(**context), None
    except Exception as exc:
        return None, str(exc)


def _normalize_details(details: Optional[Iterable[Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not details:
        return normalized
    for item in details:
        if isinstance(item, dict):
            label = item.get('label')
            value = item.get('value')
        else:
            try:
                label, value = item  # type: ignore
            except (TypeError, ValueError):
                continue
        if label is None:
            continue
        normalized.append({'label': str(label), 'value': value})
    return normalized


def _detail_pairs(context: Dict[str, Any]) -> Iterable[Tuple[str, Any]]:
    for item in context.get('details') or []:
        if isinstance(item, dict):
            label = item.get('label')
            value = item.get('value')
        else:
            try:
                label, value = item  # type: ignore
            except (TypeError, ValueError):
                continue
        if label is None:
            continue
        yield str(label), value


def _prepare_headers(custom_headers: Optional[Dict[str, Any]], default_content_type: Optional[str] = None) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if custom_headers:
        for key, value in custom_headers.items():
            headers[str(key)] = str(value)
    if default_content_type and not any(k.lower() == 'content-type' for k in headers):
        headers['Content-Type'] = default_content_type
    return headers


def _render_site_markdown(context: Dict[str, Any]) -> str:
    site_name = context.get('site_name', '未知')
    site_url = context.get('site_url', '未知')
    status_label = context.get('status_label', '-')
    status_color = context.get('status_color', 'comment')
    previous_status = context.get('previous_status', '未知')
    lines = [
        f"## {context.get('event_title', '网站监控通知')}",
        f"> **网站名称**: {site_name}",
        f"> **监控地址**: {site_url}",
        f"> **当前状态**: <font color=\"{status_color}\">{status_label}</font>",
        f"> **上次状态**: {previous_status}",
    ]
    for label, value in _detail_pairs(context):
        if value in (None, '', []):
            continue
        lines.append(f"> **{label}**: {value}")
    http_code = context.get('http_code')
    error_detail = context.get('error_detail')
    if error_detail:
        reason = str(error_detail).replace('"', '`').replace("'", '`')
        if http_code and http_code >= 400:
            reason = f"HTTP {http_code}"
        lines.append(f"> **错误详情**: `{reason}`")
    elif http_code and http_code >= 400:
        lines.append(f"> **错误详情**: `HTTP {http_code}`")
    return "\n".join(lines)


def _render_management_markdown(context: Dict[str, Any]) -> str:
    lines = [
        "## 配置变更通知",
        f"> **事件**: {context.get('event_title', '系统事件')}",
        f"> **发生时间**: {context.get('timestamp', '-')}",
    ]
    operator = context.get('operator')
    if operator:
        lines.append(f"> **操作人**: {operator}")
    for label, value in _detail_pairs(context):
        if value in (None, '', []):
            continue
        lines.append(f"> **{label}**: {value}")
    return "\n".join(lines)


def _render_feishu_text(context: Dict[str, Any]) -> str:
    lines: List[str] = [str(context.get('event_title', '监控通知'))]
    if context.get('event_category') == 'site':
        lines.append(f"网站名称: {context.get('site_name', '未知')}")
        lines.append(f"监控地址: {context.get('site_url', '未知')}")
        lines.append(f"当前状态: {context.get('status_label', '-')}")
        lines.append(f"上次状态: {context.get('previous_status', '-')}")
    if context.get('timestamp'):
        lines.append(f"发生时间: {context['timestamp']}")
    if context.get('operator'):
        lines.append(f"操作人: {context['operator']}")
    for label, value in _detail_pairs(context):
        if value in (None, '', []):
            continue
        lines.append(f"{label}: {value}")
    http_code = context.get('http_code')
    if context.get('error_detail'):
        lines.append(f"错误详情: {context['error_detail']}")
    elif http_code and http_code >= 400:
        lines.append(f"HTTP 状态码: {http_code}")
    return "\n".join(str(item) for item in lines if item is not None and str(item).strip())


def _send_channel_message(channel_cfg: Dict[str, Any], event_key: str, context: Dict[str, Any], logger) -> bool:
    channel_name = channel_cfg.get('name') or f"Channel#{channel_cfg.get('id') or '-'}"
    channel_type = channel_cfg.get('channel_type')
    webhook_url = channel_cfg.get('webhook_url')
    if not webhook_url:
        logger.warning('[通知] 渠道 %s (%s) 未配置 Webhook 地址，跳过。', channel_name, channel_type)
        return False

    headers = _prepare_headers(channel_cfg.get('custom_headers'), 'application/json')
    response = None
    success = False

    try:
        if channel_type == NotificationChannel.TYPE_QYWECHAT:
            content = _render_site_markdown(context) if context.get('event_category') == 'site' else _render_management_markdown(context)
            payload = {"msgtype": "markdown", "markdown": {"content": content}}
            response = requests.post(
                webhook_url,
                json=payload,
                headers=headers,
                timeout=CHANNEL_REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                try:
                    body = response.json()
                except ValueError:
                    body = {}
                success = isinstance(body, dict) and body.get('errcode') == 0
        elif channel_type == NotificationChannel.TYPE_DINGTALK:
            content = _render_site_markdown(context) if context.get('event_category') == 'site' else _render_management_markdown(context)
            payload = {"msgtype": "markdown", "markdown": {"title": context.get('event_title', '监控通知'), "text": content}}
            response = requests.post(
                webhook_url,
                json=payload,
                headers=headers,
                timeout=CHANNEL_REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                try:
                    body = response.json()
                except ValueError:
                    body = {}
                success = isinstance(body, dict) and body.get('errcode') == 0
        elif channel_type == NotificationChannel.TYPE_FEISHU:
            payload = {"msg_type": "text", "content": {"text": _render_feishu_text(context)}}
            response = requests.post(
                webhook_url,
                json=payload,
                headers=headers,
                timeout=CHANNEL_REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                try:
                    body = response.json()
                except ValueError:
                    body = {}
                success = isinstance(body, dict) and body.get('code') == 0
        elif channel_type == NotificationChannel.TYPE_CUSTOM:
            template = channel_cfg.get('custom_template')
            if not template:
                logger.warning('[通知] 自定义渠道 %s 缺少消息模板，已跳过。', channel_name)
                return False
            rendered, error = render_webhook_template(template, context)
            if error:
                logger.warning('[通知] 自定义渠道 %s 模板渲染失败: %s', channel_name, error)
                return False
            response = requests.post(
                webhook_url,
                data=rendered.encode('utf-8'),
                headers=headers,
                timeout=CHANNEL_REQUEST_TIMEOUT,
            )
            success = response.status_code in range(200, 300)
        else:
            logger.warning('[通知] 渠道 %s 使用了未知类型 %s，已跳过。', channel_name, channel_type)
            return False

        if success:
            logger.info('[通知] 渠道 %s (%s) 发送成功。', channel_name, channel_type)
        else:
            response_text = response.text[:200] if response is not None else '无响应'
            status_code = response.status_code if response is not None else 'N/A'
            logger.warning(
                '[通知] 渠道 %s (%s) 发送失败，状态码=%s，响应=%s',
                channel_name,
                channel_type,
                status_code,
                response_text,
            )
        return success
    except Exception as exc:
        logger.exception('[通知] 渠道 %s (%s) 发送异常: %s', channel_name, channel_type, exc)
        return False


def _dispatch_notifications(event_key: str, context: Dict[str, Any]) -> None:
    channels = [
        channel.to_message_config()
        for channel in NotificationChannel.query.filter_by(is_enabled=True).all()
        if channel.should_notify(event_key)
    ]
    if not channels:
        current_app.logger.debug('[通知] 没有启用的渠道匹配事件 %s。', event_key)
        return

    logger = current_app.logger
    workers = current_app.config.get('NOTIFICATION_WORKERS', DEFAULT_NOTIFICATION_WORKERS)
    try:
        workers = int(workers)
    except (TypeError, ValueError):
        workers = DEFAULT_NOTIFICATION_WORKERS
    workers = max(1, min(workers, len(channels)))

    if workers == 1:
        for channel_cfg in channels:
            _send_channel_message(channel_cfg, event_key, context, logger)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(_send_channel_message, channel_cfg, event_key, context, logger)
                for channel_cfg in channels
            ]
            for future in futures:
                try:
                    future.result()
                except Exception:
                    logger.exception('[通知] 渠道发送任务执行异常')


def send_notification(site_name, url, current_status_key, previous_status, *, error_detail=None, http_code=None,
                      context=None):
    meta = SITE_EVENT_META.get(current_status_key)
    if not meta:
        current_app.logger.warning('[通知] 未识别的事件类型: %s', current_status_key)
        return

    timestamp = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    detail_entries = _normalize_details(context)
    payload = {
        'event': current_status_key,
        'event_category': 'site',
        'event_title': meta['title'],
        'site_name': site_name,
        'site_url': url,
        'status_key': current_status_key,
        'status_label': meta['status_label'],
        'status_color': meta['status_color'],
        'status_text': meta['status_label'],
        'previous_status': previous_status,
        'severity': meta['severity'],
        'timestamp': timestamp,
        'http_code': http_code,
        'error_detail': error_detail,
        'details': detail_entries,
        'extra': detail_entries,
        'site': {'name': site_name, 'url': url},
        'status': {
            'key': current_status_key,
            'label': meta['status_label'],
            'previous': previous_status,
        },
    }
    _dispatch_notifications(current_status_key, payload)


def send_management_notification(event_title, *, operator=None, details=None):
    timestamp = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    detail_entries = _normalize_details(details)
    payload = {
        'event': 'management',
        'event_category': 'management',
        'event_title': event_title,
        'operator': operator or '系统',
        'timestamp': timestamp,
        'details': detail_entries,
        'extra': detail_entries,
    }
    _dispatch_notifications('management', payload)


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
    raw_suppression = current_app.config.get('ALERT_SUPPRESSION_SECONDS', 600)
    try:
        alert_suppression_seconds = int(raw_suppression)
    except (TypeError, ValueError):
        alert_suppression_seconds = 0
    alert_suppression_seconds = max(0, alert_suppression_seconds)

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
        now_utc = datetime.datetime.utcnow()
        now_epoch = now_utc.timestamp()
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
            prev_notifications = prev.get("last_notifications") or {}
            last_notifications = {}
            if isinstance(prev_notifications, dict):
                for event_key, raw_value in prev_notifications.items():
                    if isinstance(raw_value, (int, float)):
                        last_notifications[event_key] = float(raw_value)
                        continue
                    if isinstance(raw_value, datetime.datetime):
                        last_notifications[event_key] = raw_value.timestamp()
                        continue
                    try:
                        parsed = datetime.datetime.fromisoformat(str(raw_value))
                    except (TypeError, ValueError):
                        continue
                    else:
                        last_notifications[event_key] = parsed.timestamp()

            def _should_send(event_key: str) -> bool:
                if alert_suppression_seconds <= 0:
                    return True
                last_ts = last_notifications.get(event_key)
                if last_ts is None:
                    return True
                return (now_epoch - last_ts) >= alert_suppression_seconds

            def _mark_sent(event_key: str) -> None:
                last_notifications[event_key] = now_epoch
                suppression_log_key = f"{event_key}__suppression_log"
                if suppression_log_key in last_notifications:
                    del last_notifications[suppression_log_key]

            def _log_suppressed(event_key: str) -> None:
                if alert_suppression_seconds <= 0:
                    return
                last_ts = last_notifications.get(event_key)
                if last_ts is None:
                    return
                suppression_log_key = f"{event_key}__suppression_log"
                last_logged = last_notifications.get(suppression_log_key)
                throttle_window = max(30, min(alert_suppression_seconds, 300))
                if last_logged is not None and (now_epoch - last_logged) < throttle_window:
                    return
                elapsed = max(0, now_epoch - last_ts)
                remaining = max(0, alert_suppression_seconds - elapsed)
                event_meta = SITE_EVENT_META.get(event_key, {})
                label = event_meta.get('status_label') or event_meta.get('title') or event_key
                current_app.logger.info(
                    '[告警抑制] 站点 %s 的 %s 告警在 %.0f 秒前已发送，距离下一次通知还需约 %.0f 秒。',
                    site_name,
                    label,
                    elapsed,
                    remaining,
                )
                last_notifications[suppression_log_key] = now_epoch

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
                "total_checks": total_checks,
                "last_notifications": last_notifications,
            }

            down_duration_str = _format_duration(now - down_since_dt) if down_since_dt else None
            slow_duration_str = _format_duration(now - slow_since_dt) if slow_since_dt else None

            if is_down and not notification_sent:
                if failure_count >= fail_consecutive or fails_in_window >= window_threshold:
                    if not _should_send('down'):
                        _log_suppressed('down')
                    else:
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
                        _mark_sent('down')
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
                    if not _should_send('slow'):
                        _log_suppressed('slow')
                    else:
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
                        _mark_sent('slow')
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
