# web-monitor/run.py

from app import create_app
from app.services import initialize_site_statuses
app = create_app()
if __name__ == '__main__':
    print("监控面板服务已启动, 请访问 http://127.0.0.1:8080")
    # Flask 默认端口是 5000，用 host='0.0.0.0' 来允许外部访问
    initialize_site_statuses(app)
    app.run(host='0.0.0.0', port=8080)
