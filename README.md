# Web Monitor (网站健康监控面板)

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python Version](https://img.shields.io/badge/Python-3.9+-brightgreen.svg)
![Framework](https://img.shields.io/badge/Framework-Flask-orange.svg)

一个轻量、美观且功能强大的自托管网站健康监控面板。使用 Python 和 Flask 构建，提供实时状态概览、历史数据可视化、安全的后台管理和灵活的告警通知功能。

A lightweight, beautiful, and powerful self-hosted website health monitoring dashboard. Built with Python and Flask, it provides a real-time status overview, historical data visualization, a secure admin backend, and flexible alerting.

---

![Dashboard Screenshot](https://fastly.jsdelivr.net/gh/th815/images//blogCleanShot%202025-10-14%20at%2018.42.44.png)

## ✨ 功能特性 (Features)

*   **实时状态墙**: 以卡片形式直观展示所有网站的当前状态（正常、访问过慢、无法访问）、响应时间和上次检查时间。
*   **精确的历史时间轴**: 使用 ECharts 自定义系列，将每个站点的在线、慢速、宕机和无数据时段渲染为精确的连续时间块。
*   **聚合统计图表**: 动态对比多个站点的可用率（%）和响应时间趋势。
*   **灵活的时间选择器**: 支持预设时间范围（1小时、6小时、1天、7天、1个月）和自定义日期范围查询。
*   **安全的后台管理**:
    *   基于 **Flask-Admin** 和 **Flask-Login** 构建，提供安全的管理员登录认证。
    *   在后台轻松添加、编辑、删除和禁用受监控的网站。
    *   查看详细的原始监控日志，支持搜索和筛选。
*   **动态主题切换**: 管理员可以根据个人喜好在后台一键切换超过20种界面主题。
*   **企业微信/Webhook 告警**:
    *   当网站连续多次无法访问时，通过 Webhook 发送告警通知。
    *   当网站从故障中恢复时，发送恢复通知。
    *   内置防抖机制（连续失败N次后才告警），避免网络波动造成的频繁骚扰。
*   **后台定时任务**: 使用 **APScheduler** 自动执行周期性健康检查和历史数据清理任务。
*   **数据库平滑升级**: 集成 **Flask-Migrate**，修改数据模型后无需删库跑路，一条命令即可热更新数据库结构，保留所有历史数据。

## 🛠️ 技术栈 (Tech Stack)

*   **后端 (Backend)**: Python 3.9+, Flask, SQLAlchemy, Flask-Admin, Flask-Login, Flask-Migrate, APScheduler
*   **前端 (Frontend)**: HTML5, CSS3, Vanilla JavaScript, ECharts, Flatpickr
*   **数据库 (Database)**: SQLite (默认), 可通过 SQLAlchemy 轻松配置为 PostgreSQL, MySQL 等。

## 🚀 快速开始 (Getting Started)

请按照以下步骤在你的服务器或本地计算机上部署和运行本项目。

### 1. 先决条件 (Prerequisites)

*   Git
*   Python 3.9 或更高版本

### 2. 安装步骤 (Installation)

1.  **克隆仓库**
    ```bash
    git clone https://github.com/YOUR_USERNAME/web-monitor.git
    cd web-monitor
    ```

2.  **创建并激活虚拟环境**
    *   **Linux / macOS**:
        ```bash
        python3 -m venv .venv
        source .venv/bin/activate
        ```
    *   **Windows**:
        ```bash
        python -m venv .venv
        .\.venv\Scripts\activate
        ```

3.  **安装依赖**
    ```bash
    pip install -r requirements.txt
    ```

### 3. 应用配置 (Configuration)

1.  **创建 `.flaskenv` 文件**
    在项目根目录下创建一个名为 `.flaskenv` 的文件，用于设置环境变量。这比 `export` 命令更方便。
    ```
    FLASK_APP=run.py
    # FLASK_DEBUG=1  # 在开发时可以取消此行注释
    ```

2.  **编辑 `config.py`**
    *   **`SECRET_KEY`**: **（必须修改）** 这是 Flask 应用用于加密会话的密钥。请务必将其更改为一个长而随机的字符串。你可以使用以下命令生成：
        ```bash
        python -c 'import secrets; print(secrets.token_hex(16))'
        ```
    *   **`QYWECHAT_WEBHOOK_URL`**: (可选) 填入你的企业微信群机器人的 Webhook URL 以启用告警通知功能。
    *   **`MONITOR_INTERVAL_SECONDS`**: (可选) 健康检查频率（秒）。可通过环境变量 MONITOR_INTERVAL_SECONDS 配置，默认 20 秒。

### 4. 数据库初始化与迁移 (Database Initialization & Migration)

本项目使用 **Flask-Migrate** 管理数据库结构。

1.  **首次初始化 (仅需执行一次)**
    此命令会创建 `migrations` 文件夹来存放迁移脚本。
    ```bash
    flask db init
    ```

2.  **生成并应用首次迁移**
    此命令会根据 `models.py` 创建第一个版本的数据库结构，并应用它。
    ```bash
    flask db migrate -m "Initial migration"
    flask db upgrade
    ```

3.  **填充初始数据**
    运行自定义命令来创建默认管理员和监控站点。
    ```bash
    flask init-db
    ```
    执行后会创建一个默认管理员账户：
    *   **用户名**: `admin`
    *   **密码**: `changeme`

    **强烈建议首次登录后立即在后台修改默认密码！**

### 5. 运行应用 (Running the Application)

#### 开发环境

用于本地测试和开发。Flask 会启动一个内置的开发服务器。

```bash
flask run --host=0.0.0.0 --port=8080
```
应用将在 `http://127.0.0.1:8080` 上运行。

#### 生产环境 (Gunicorn + Nginx)

**强烈建议**在生产环境中使用专业的 WSGI 服务器（如 Gunicorn）和反向代理（如 Nginx）。

1.  **使用 Gunicorn 运行**
    ```bash
    gunicorn -w 4 -b 0.0.0.0:8080 "app:create_app()"
    ```
    *   `-w 4`: 启动 4 个工作进程 (通常设置为 `2 * CPU核心数 + 1`)。
    *   `-b 0.0.0.0:8080`: 绑定到所有网络接口的 8080 端口。

2.  **配置 Nginx 作为反向代理**
    创建一个新的 Nginx 配置文件，例如 `/etc/nginx/sites-available/web-monitor`：
    ```nginx
    server {
        listen 80;
        server_name your_domain.com; # 替换为你的域名

        location / {
            proxy_pass http://127.0.0.1:8080;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
    ```
    然后启用该站点并重启 Nginx：
    ```bash
    sudo ln -s /etc/nginx/sites-available/web-monitor /etc/nginx/sites-enabled
    sudo nginx -t # 测试配置是否正确
    sudo systemctl restart nginx
    ```

## 🗄️ 数据库维护 (Database Maintenance)

当你修改了 `app/models.py` 中的数据模型后（例如添加或删除字段），请遵循以下流程来平滑升级数据库，而**不会丢失任何数据**。

1.  **生成迁移脚本**
    ```bash
    # -m "..." 是对本次变更的简短描述
    flask db migrate -m "Add a new feature or fix a model"
    ```

2.  **应用迁移**
    ```bash
    flask db upgrade
    ```
    你的数据库现在已经更新到最新结构了！

## 📜 开源协议 (License)

本项目采用 **MIT License** 开源协议。

这意味着你可以自由地使用、复制、修改、合并、出版、分发、再许可和/或销售本软件的副本，只需在所有副本或主要部分中包含原始的版权和许可声明即可。

详情请参阅 [LICENSE](LICENSE) 文件。

## 🤝 贡献 (Contributing)

我们非常欢迎各种形式的贡献！

1.  Fork 本项目
2.  创建你的功能分支 (`git checkout -b feature/AmazingFeature`)
3.  提交你的更改 (`git commit -m 'Add some AmazingFeature'`)
4.  推送到分支 (`git push origin feature/AmazingFeature`)
5.  开启一个 Pull Request

对于重大更改，请先开启一个 Issue 来讨论你想要改变的内容。

---
*由 TIANHAO DEVOPS TOOLS 强力驱动*
