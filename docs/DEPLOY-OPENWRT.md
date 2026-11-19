# OpenWrt 部署指南

本服务为轻量 Python 服务（约 100MB 磁盘占用），适合运行在 x86 软路由 / 迷你主机上。
提供两种部署方式，**推荐 Docker**。

## 架构总览

```
微信小程序 ──HTTPS:443──> Nginx/Caddy ──> 127.0.0.1:8080
                        ├── FastAPI 服务
                        │     ├── 微信登录 (调用微信 jscode2session)
                        │     ├── 分析任务 (后台线程异步执行)
                        │     └── 报告生成 (Markdown + Word)
                        ├── 通义千问 DashScope API (云端大模型)
                        └── DuckDuckGo 搜索 (客户背调)
```

## 前置准备

1. 确认路由器可访问外网（大模型 API 与搜索都需要）。
2. 准备配置信息：Docker Compose 使用项目的 `backend/.env`；原生安装后编辑 `/opt/ka-agent/.env`（不是源码目录的 `.env`）：
   - `WX_APPID` / `WX_SECRET`：见 [微信小程序配置](WECHAT-SETUP.md)
   - `JWT_SECRET`：随机长字符串，可用 `openssl rand -hex 32` 生成
   - `LLM_API_KEY`：阿里云百炼平台 https://bailian.console.aliyun.com 开通并创建 API Key
     （新用户有免费额度；也可换成 DeepSeek 等任意 OpenAI 兼容接口，改 `LLM_BASE_URL` 与 `LLM_MODEL` 即可）

## 方式 A：Docker 部署（推荐）

x86 软路由安装 Docker：

```sh
opkg update
opkg install dockerd docker-compose
/etc/init.d/dockerd enable && /etc/init.d/dockerd start
```

部署服务（把整个项目目录传到路由器，如 /opt/classin-ka-agent）：

```sh
cd /opt/classin-ka-agent
vi backend/.env   # 填入配置
cd backend/deploy
docker-compose up -d --build
```

验证：

```sh
curl http://127.0.0.1:8080/api/health
# 期望输出 {"status":"ok","wx_configured":true,"llm_configured":true,...}
```

升级：`docker-compose up -d --build` 重新构建即可，数据保存在项目根目录 `data/` 不会丢失。

## 方式 B：原生部署（无 Docker）

> 当前原生安装脚本仅安装和启动 Web 服务，不安装或管理分析 Worker。Web 启动和健康检查成功不代表分析任务可执行。需要完整分析功能时优先使用方式 A 的 Compose（包含 Web 与 Worker）；仅当你已单独部署 `backend/worker.py` 常驻服务，并确保它与 Web 使用相同配置及同一 `DATA_DIR` 时，才采用原生方式。本次配置修复不补齐 Worker 服务管理。

```sh
cd /opt/classin-ka-agent/backend
sh deploy/install-openwrt.sh
vi /opt/ka-agent/.env          # 填入配置
/etc/init.d/ka-agent start
```

首次安装会创建权限为 600、密钥为空的 `/opt/ka-agent/.env` 配置骨架，不依赖 `.env.example`。启动前必须填写随机 `JWT_SECRET`（至少 32 字节）、微信配置及模型 API Key，保留 `HOST=127.0.0.1`。配置由 `/bin/sh` 加载，特殊字符需正确引用。重复安装不会覆盖已有 `.env`；修改配置后执行 `/etc/init.d/ka-agent restart`，密钥轮换会使旧登录失效。

日志：`logread -f`；重启自启已自动配置。

## 让小程序能访问到服务

微信小程序对后端地址有硬性要求，分两个阶段：

### 开发调试阶段

与正式环境一样配置有效证书的 HTTPS 反向代理。未就绪时仅在服务器本机访问健康检查接口，不通过 HTTP 传输微信登录 code、Bearer Token 或客户数据。Docker 仅监听宿主机回环地址，反向代理需在同一宿主机运行。

### 正式使用阶段（必须 HTTPS + 备案域名）

小程序正式版只允许请求**已备案的 HTTPS 域名**，且需在微信公众平台「开发设置 → 服务器域名」登记。家用宽带环境的可行路径：

- **有公网 IP**：DDNS 解析 + 路由器端口转发 443 → Caddy/Nginx 反向代理到 8080，自动申请 Let's Encrypt 证书。注意域名需完成 ICP 备案才能被小程序使用。
- **无公网 IP**：用一台有备案域名的轻量云服务器做 frp 内网穿透中转，或直接把后端部署到该云服务器（本服务资源占用很低，1核2G 足够）。
- 纯内网穿透服务（如 Cloudflare Tunnel）的域名通常无法备案，小程序正式环境不可用，仅适合开发调试。

> 不要关闭域名或证书校验来长期使用 HTTP。升级前参阅 [安全迁移清单](SECURITY-MIGRATION.md)。

## 常见问题

- **pip 安装慢**：脚本已默认使用阿里云镜像；Docker 构建时可在 Dockerfile 的 pip 命令后加 `-i https://mirrors.aliyun.com/pypi/simple/`
- **搜索没结果**：DuckDuckGo 在部分网络环境不通，可在 `.env` 设 `SEARCH_ENABLED=false`，Agent 会基于行业常识分析并注明信息有限
- **时间不同步导致 JWT/HTTPS 报错**：确认 OpenWrt 已启用 NTP（系统 → 时间同步）
- **修改 .env 后不生效**：Docker 需 `docker-compose up -d --force-recreate`（仅 restart 不会更新容器环境变量）；原生需 `/etc/init.d/ka-agent restart`
