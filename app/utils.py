# web-monitor/app/utils.py
import datetime
from datetime import timezone

def to_gmt8(utc_dt):
    """将 UTC datetime 对象转换为 GMT+8 时区的 datetime 对象"""
    if utc_dt is None:
        return None
    # 创建一个 UTC+8 的时区对象
    gmt8_tz = timezone(datetime.timedelta(hours=8))
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(gmt8_tz)

