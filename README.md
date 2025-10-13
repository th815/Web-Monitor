# Web Monitor (网站健康监控面板)

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python Version](https://img.shields.io/badge/Python-3.9+-brightgreen.svg)
![Framework](https://img.shields.io/badge/Framework-Flask-orange.svg)

一个轻量、美观且功能强大的自托管网站健康监控面板。使用 Python 和 Flask 构建，提供实时状态概览、历史数据可视化和安全的后台管理功能。

A lightweight, beautiful, and powerful self-hosted website health monitoring dashboard. Built with Python and Flask, it provides a real-time status overview, historical data visualization, and a secure admin backend.

---

[此处插入项目截图，展示监控面板的主界面]
*(建议截图尺寸: 1280x720px)*

## ✨ 功能特性 (Features)

*   **实时状态墙**: 以卡片形式直观展示所有受监控网站的当前状态（正常、访问过慢、无法访问）和响应时间。
*   **历史数据可视化**:
    *   **Uptime 历史条**: 精确展示过去一段时间内每个站点的在线/离线记录。
    *   **ECharts 动态图表**: 对比多个站点的可用率和平均响应时间。
*   **灵活的时间选择器**: 支持预设时间范围（1小时、1天、7天等）和自定义日期范围查询。
*   **安全的后台管理**:
    *   基于 Flask-Admin 和 Flask-Login 构建，提供安全的管理员登录认证。
    *   在后台轻松添加、编辑、删除和禁用受监控的网站。
    *   查看详细的原始监控日志。
*   **动态主题切换**: 管理员可以根据个人喜好在后台一键切换界面主题。
*   **后台定时任务**: 使用 APScheduler 自动执行健康检查和数据清理任务。
*   **易于扩展**: 可通过配置轻松对接企业微信等通知渠道（当前已预留 Webhook 逻辑）。

## 🛠️ 技术栈 (Tech Stack)

*   **后端 (Backend)**: Python 3.9+, Flask, SQLAlchemy, Flask-Admin, Flask-Login, APScheduler
*   **前端 (Frontend)**: HTML5, CSS3, Vanilla JavaScript, ECharts, Flatpickr
*   **数据库 (Database)**: SQLite (默认), 可轻松配置为 PostgreSQL, MySQL 等。

## 🚀 部署与运行 (Getting Started)

请按照以下步骤在你的服务器或本地计算机上部署和运行本项目。

### 1. 先决条件 (Prerequisites)

*   Git
*   Python 3.9 或更高版本

### 2. 安装步骤 (Installation)

1.  **克隆仓库**
    ```bash
    git clone [你的项目Git仓库地址]
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
    首先，生成 `requirements.txt` 文件（如果项目中还没有的话），然后安装。
    ```bash
    # (可选，如果 requirements.txt 不存在)
    # pip freeze > requirements.txt 
    
    pip install -r requirements.txt
    ```

### 3. 应用配置 (Configuration)

所有配置项都在 `config.py` 文件中。

1.  **复制示例配置 (如果需要)**
    如果你有 `config.py.example`，请先复制它：
    `cp config.py.example config.py`

2.  **编辑 `config.py`**
    *   **`SECRET_KEY`**: **（必须修改）** 这是 Flask 应用用于加密会话（Session）的密钥。请务必将其更改为一个长而随机的字符串。你可以使用 `python -c 'import os; print(os.urandom(24))'` 来生成。
    *   **`WECHAT_WEBHOOK_URL`**: (可选) 填入你的企业微信群机器人的 Webhook URL 以启用通知功能。
    *   **`MONITOR_INTERVAL_SECONDS`**: (可选) 健康检查的频率，单位为秒，默认为 60。

### 4. 数据库初始化

本项目包含一个自定义的 Flask 命令，用于初始化数据库并创建第一个管理员用户。

```bash
flask init-db
```
执行此命令后，会：
*   创建 `instance/monitor.db` 数据库文件。
*   创建所有数据表。
*   添加一个默认管理员账户：
    *   **用户名**: `admin`
    *   **密码**: `changeme`

**强烈建议首次登录后立即在后台修改默认密码！**

### 5. 运行应用 (Running the Application)

#### 开发环境

用于本地测试和开发。Flask 会启动一个内置的开发服务器。

```bash
python run.py
```
应用将在 `http://127.0.0.1:8080` 上运行。

#### 生产环境

**强烈建议**在生产环境中使用专业的 WSGI 服务器，如 Gunicorn 或 uWSGI，并使用 Nginx 作为反向代理。

**使用 Gunicorn 运行:**

1.  首先，确保 Gunicorn 已安装：
    ```bash
    pip install gunicorn
    ```

2.  运行应用：
    ```bash
    gunicorn -w 4 -b 0.0.0.0:8080 "app:create_app()"
    ```
    *   `-w 4`: 启动 4 个工作进程 (可根据你的 CPU 核心数调整)。
    *   `-b 0.0.0.0:8080`: 绑定到所有网络接口的 8080 端口。
    *   `"app:create_app()"`: 指向我们的应用工厂函数。

现在，你可以配置 Nginx 将外部流量（例如来自 `yourdomain.com` 的请求）代理到 Gunicorn 正在监听的 `http://127.0.0.1:8080`。


---

### 生产环境 (使用 Systemd 和 Nginx)

为了保证应用在后台稳定运行并能开机自启，推荐使用 `Systemd` 来管理 Gunicorn 进程。

**1. 创建 Systemd 服务文件**

创建 `/etc/systemd/system/web-monitor.service` 文件，并填入以下内容 (请根据你的实际路径和用户名修改):

```bash
[Unit]
Description=Gunicorn instance to serve Web Monitor
After=network.target

[Service]
User=youruser
Group=youruser
WorkingDirectory=/home/youruser/web-monitor
Environment="PATH=/home/youruser/web-monitor/.venv/bin"
ExecStart=/home/youruser/web-monitor/.venv/bin/gunicorn --workers 3 --bind unix:web-monitor.sock -m 007 "app:create_app()"
Restart=always

[Install]
WantedBy=multi-user.target
```

**2. 启动并启用服务**

```bash
# 重新加载 systemd 配置
sudo systemctl daemon-reload

# 立即启动服务
sudo systemctl start web-monitor

# 检查服务状态以确认运行正常
sudo systemctl status web-monitor

# 设置开机自启
sudo systemctl enable web-monitor
```

**3. 配置 Nginx 作为反向代理**


## 📜 开源协议 (License)

本项目采用 **MIT License** 开源协议。

这意味着你可以自由地使用、复制、修改、合并、出版、分发、再许可和/或销售本软件的副本，只需在所有副本或主要部分中包含原始的版权和许可声明即可。

详情请参阅 [LICENSE](LICENSE) 文件。

## 🤝 贡献 (Contributing)

欢迎提交 Pull Request。对于重大更改，请先开启一个 Issue 来讨论你想要改变的内容。

---
*由 TIANHAO DEVOPS TOOLS 强力驱动*
