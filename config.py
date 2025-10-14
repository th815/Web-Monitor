# web-monitor/config.py

import os

# 获取项目根目录的绝对路径
basedir = os.path.abspath(os.path.dirname(__file__))
# 【新增】Flask-Admin 主题设置
# 从这里选择你喜欢的主题: https://bootswatch.com/
# 推荐: cerulean, cosmo, flatly, journal, litera, lumen, lux, materia, minty, pulse, sandstone, simplex, solar, spacelab, united, yeti
# 暗黑主题: cyborg, darkly, slate, solar
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
MONITOR_INTERVAL_SECONDS = 60
SLOW_RESPONSE_THRESHOLD_SECONDS = 3.0
DATA_RETENTION_DAYS = 30

# 数据库配置
# 我们将数据库文件放在 instance 文件夹下，这是Flask推荐的做法
SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'instance', 'monitoring_data.db')
SQLALCHEMY_TRACK_MODIFICATIONS = False
