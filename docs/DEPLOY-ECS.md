# 阿里云 ECS 部署指南（Docker 方式）

适用场景：后端部署在阿里云 ECS（国内地域），微信小程序通过 HTTPS 备案域名访问。

## 架构总览

```
微信小程序 ──HTTPS(443)──> ECS: nginx ──> 127.0.0.1:8080 (FastAPI 容器)
                                          ├── 微信登录 (jscode2session)
                                          ├── 分析任务 (后台异步执行)
                                          ├── 报告生成 (Markdown + Word)
                                          └── 大模型 API (aixj.vip)
数据持久化：项目根目录 data/（SQLite + 生成的 Word 报告）
```

端口规划：公网只开放 22（SSH）、80、443。8080 仅容器与 nginx 内部使用，**不对公网开放**。

---

## 第 0 步：准备工作清单

开始部署前，确认/着手以下四件事（域名备案周期最长，建议最先启动）：

1. **购买 ECS**：地域选国内（就近即可），配置 2 核 2GB 起步足够，系统选 Ubuntu 22.04/24.04 LTS。
2. **购买域名并 ICP 备案**（微信正式版的硬性要求，周期约 1–2 周）：
   - 阿里云「域名注册」购买一个域名（.top/.cn 均可，几十元/年）
   - 完成实名认证后，在阿里云「ICP 备案」提交备案申请
   - 备案期间仅做本机健康检查，不通过公网 HTTP 传输登录信息或客户数据
3. **生成小程序 AppSecret**：
   - 登录 [微信公众平台](https://mp.weixin.qq.com)（小程序账号）
   - 「开发管理 → 开发设置 → AppSecret」→ 生成（需管理员扫码）
   - **只显示一次**，保存好后填入 ECS 上 `backend/.env` 的 `WX_SECRET`
4. **确认 backend/.env 内容**（本项目已配置好大部分，需核对）：
   - `WX_APPID=wx8dcf123fb338fc61`（已填）
   - `WX_SECRET=` ← 填上一步生成的 AppSecret
   - `LLM_API_KEY`（已填，已验证可用）
   - `SEARCH_ENABLED=false`（已关闭，国内 ECS 无法访问 DuckDuckGo）

---

## 第 1 步：ECS 安装 Docker

SSH 登录 ECS 后，逐段粘贴执行：

```sh
# 安装 Docker（使用阿里云镜像站，国内快）
curl -fsSL https://get.docker.com | sh -s docker --mirror Aliyun
```

```sh
# 启动并设置开机自启
sudo systemctl enable --now docker
```

```sh
# 配置镜像加速器（必须，否则拉取 python 基础镜像很慢或失败）
# 专属加速地址获取：阿里云控制台 → 容器镜像服务 → 镜像工具 → 镜像加速器
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": ["https://你的专属加速地址.mirror.aliyuncs.com"]
}
EOF
sudo systemctl restart docker
```

```sh
# 验证（两条都要有输出）
docker version
docker compose version
```

---

## 第 2 步：上传代码到 ECS

在**你自己的 Mac 终端**执行（把 `ECS公网IP` 换成实际 IP）：

```sh
cd ~/Downloads/Code
tar czf classin-ka-agent.tar.gz \
  --exclude 'classin-ka-agent/backend/.venv' \
  --exclude 'classin-ka-agent/backend/__pycache__' \
  --exclude 'classin-ka-agent/data' \
  classin-ka-agent
scp classin-ka-agent.tar.gz root@ECS公网IP:/opt/
```

> 说明：排除 `.venv`（Mac 的虚拟环境 Linux 用不了）和本地 `data/`（开发期测试数据不带过去，服务器上会全新创建）。

回到 **ECS** 上解包：

```sh
cd /opt && tar xzf classin-ka-agent.tar.gz && ls classin-ka-agent
```

---

## 第 3 步：核对配置

在 ECS 上：

```sh
cd /opt/classin-ka-agent/backend
vi .env  # 仅在服务器本地编辑，不要将密钥输出到聊天或日志
```

逐项确认：

- `WX_APPID=wx8dcf123fb338fc61`
- `WX_SECRET=` 后面是真实 AppSecret（**不能还是占位符**）
- `LLM_API_KEY=` 后面是 sk- 开头的 Key
- `JWT_SECRET=` 必须设置为独立的随机密钥（至少 32 字节），可在服务器本地使用 `openssl rand -hex 32` 生成；不可使用旧默认值或提交到 Git
- `SEARCH_ENABLED=false`
- `DAILY_FREE_LIMIT=5`（每人每天免费分析次数，想调多少改多少，0 = 不限制）

顺手在 ECS 上验证大模型接口连通性（国内 ECS 与本机的网络环境不同，务必测一次）：

```sh
source <(grep -E '^LLM_(BASE_URL|API_KEY)=' .env | sed 's/^/export /')
curl -sS -m 20 "$LLM_BASE_URL/models" -H "Authorization: Bearer $LLM_API_KEY" | head -c 200
```

能返回模型列表 JSON 即通。若超时，说明该 ECS 访问 aixj.vip 受限，需更换大模型接口（如阿里云百炼 DashScope：`LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`）。

---

## 第 4 步：启动服务

在 ECS 上：

```sh
cd /opt/classin-ka-agent/backend/deploy
docker compose up -d --build
```

```sh
# 看日志，出现 "Uvicorn running on http://0.0.0.0:8080" 即成功
docker compose logs -f --tail 50
```

```sh
# 健康检查
curl http://127.0.0.1:8080/api/health
```

期望输出（`wx_configured` 必须为 true；注意占位符没改时它也会显示 true，所以要以第 3 步人工核对为准）：

```json
{"status":"ok","wx_configured":true,"llm_configured":true,"model":"gpt-5.6-sol"}
```

---

## 第 5 步：上线前安全检查

不要开放公网 8080，也不要通过关闭域名/TLS 校验来发送真实登录凭据或客户数据。Docker 模板只绑定宿主机 127.0.0.1；nginx 应安装在同一宿主机。未配置 HTTPS 域名前仅使用服务器本地健康检查，完整联调等待第 6 步完成。

已有部署升级请先阅读 [安全迁移清单](SECURITY-MIGRATION.md)。缺少强 JWT_SECRET 时新版本会拒绝启动；小程序未填入 HTTPS 地址时会拒绝联网。

---

## 第 6 步：域名解析 + HTTPS（备案通过后）

1. **域名解析**：阿里云「云解析 DNS」→ 添加 A 记录，如 `api.你的域名` → ECS 公网 IP
2. **申请免费证书**：阿里云「数字证书管理服务」→ 免费证书 → 为 `api.你的域名` 申请（需 DNS 验证）→ 下载 **Nginx 格式**证书，得到两个文件：`api.你的域名.pem` 和 `api.你的域名.key`
3. **上传证书到 ECS**（在本机执行，路径按实际下载位置调整）：

```sh
scp ~/Downloads/api.你的域名.pem ~/Downloads/api.你的域名.key root@ECS公网IP:/etc/nginx/ssl/
```

（若 ECS 上还没有 `/etc/nginx/ssl/` 目录，先在 ECS 执行 `sudo mkdir -p /etc/nginx/ssl`）

4. **安装并配置 nginx**（在 ECS 上）：

```sh
sudo apt update && sudo apt install -y nginx
```

```sh
sudo tee /etc/nginx/conf.d/ka-agent.conf <<'EOF'
server {
    listen 80;
    server_name api.你的域名;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name api.你的域名;

    ssl_certificate     /etc/nginx/ssl/api.你的域名.pem;
    ssl_certificate_key /etc/nginx/ssl/api.你的域名.key;

    client_max_body_size 5m;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 300s;
    }
}
EOF
```

> 粘贴前把两处 `api.你的域名` 换成真实域名。

```sh
sudo nginx -t && sudo systemctl enable --now nginx
```

5. **安全组**：入方向放行 `80` 与 `443`（授权对象 0.0.0.0/0），确认 8080 未开放

```sh
# ECS 上验证 HTTPS
curl -I https://api.你的域名/api/health
# 本机浏览器访问 https://api.你的域名/api/health 应返回 JSON
```

---

## 第 7 步：微信公众平台配置 + 小程序上线

1. 微信公众平台 →「开发管理 → 开发设置 → 服务器域名」：
   - `request 合法域名`：`https://api.你的域名`
   - `downloadFile 合法域名`：`https://api.你的域名`
2. 修改 `miniprogram/utils/config.js`：
   ```js
   API_BASE_URL: 'https://api.你的域名'
   ```
3. 微信开发者工具点「上传」→ 公众平台「版本管理」→ 提交审核 → 审核通过后发布

---

## 常用运维操作

```sh
cd /opt/classin-ka-agent/backend/deploy
```

```sh
# 代码更新：本机重新打包上传覆盖后，重建容器即可
docker compose up -d --build
```

```sh
# 查看日志
docker compose logs -f --tail 100
```

```sh
# 备份数据（数据库 + 报告）
tar czf ka-backup-$(date +%F).tar.gz -C /opt/classin-ka-agent data
```

```sh
# 重启服务
docker compose restart
```

---

## 故障排查

| 现象 | 排查方向 |
| --- | --- |
| 登录报"微信登录失败: invalid appid" | `.env` 的 `WX_APPID`/`WX_SECRET` 不正确或未生效（改完要 `docker compose up -d` 重启容器） |
| 分析一直卡在"搜索客户信息…" | 确认 `SEARCH_ENABLED=false` 已生效 |
| 分析报"大模型调用失败" | 在 ECS 上执行第 3 步的 curl 验证；检查 Key 余额/接口是否变更 |
| 小程序提示网络异常 | 依次确认：域名已解析、证书有效、安全组放行 443、微信后台已配置合法域名、`config.js` 地址无多余斜杠 |
| 下载 Word 失败 | 微信后台 `downloadFile 合法域名` 是否配置；`data/reports/` 下文件是否存在（`docker compose exec ka-agent ls /data/reports`） |
