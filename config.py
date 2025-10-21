# web-monitor/config.py

import os

# 获取项目根目录的绝对路径
basedir = os.path.abspath(os.path.dirname(__file__))

# Flask-Admin 主题设置
# 主题可选: https://bootswatch.com/
FLASK_ADMIN_SWATCH = 'lumen'

# 基础配置
SECRET_KEY = 'a-super-secret-key-that-you-should-change'
QYWECHAT_WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE" # 记得替换成你的Key

# SITES_TO_MONITOR = [
#     {"name": "谷歌", "url": "https://www.google.com"},
#     {"name": "GitHub", "url": "https://www.github.com"},
#     {"name": "ERP系统", "url": "https://erp.huimaisoft.com"},
#     {"name": "SCM系统", "url": "https://scm-pc.huimaisoft.com"},
#     {"name": "不存在的网站", "url": "http://thiswebsitedoesnotexist.com"},
#     {"name": "响应慢的网站", "url": "http://httpbin.org/delay/5"},
# ]
# 健康检查频率（秒）。可通过环境变量 MONITOR_INTERVAL_SECONDS 覆盖，默认 20 秒以更快触发告警。
MONITOR_INTERVAL_SECONDS = 60
MONITOR_INTERVAL_SECONDS = int(os.getenv('MONITOR_INTERVAL_SECONDS', '20'))
SLOW_RESPONSE_THRESHOLD_SECONDS = 3.0  # 响应超过该阈值判定为“访问过慢”

# 告警判定参数（更精准，降低误报与漏报）
FAILURE_CONFIRMATION_THRESHOLD = 3       # 连续失败 N 次后告警
FAILURE_WINDOW_SIZE = 5                  # 最近 M 次检查的窗口大小
FAILURE_WINDOW_THRESHOLD = 3             # 最近 M 次中失败次数达到 K 次也告警（捕捉短时故障）
RECOVERY_CONFIRMATION_THRESHOLD = 2      # 连续成功 N 次后才发送“恢复”
QUICK_RETRY_COUNT = 1                    # 单次检查失败后，快速重试次数
QUICK_RETRY_DELAY_SECONDS = 2            # 快速重试间隔（秒）

# 数据保留
DATA_RETENTION_DAYS = 30

# 数据库配置（将数据库文件放在 instance 目录下）
SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'instance', 'monitoring_data.db')
SQLALCHEMY_TRACK_MODIFICATIONS = False
