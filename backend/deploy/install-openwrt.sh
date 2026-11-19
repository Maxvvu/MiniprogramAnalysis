#!/bin/sh
# ClassIn KA 客户分析 Agent —— OpenWrt 原生安装脚本（不用 Docker 时使用）
# 用法：在 backend 目录下执行  sh deploy/install-openwrt.sh
set -e

INSTALL_DIR=/opt/ka-agent

[ "$(id -u)" = "0" ] || { echo "请用 root 执行本脚本"; exit 1; }

echo "==> 1/5 安装 Python3 与 pip"
opkg update
opkg install python3 python3-pip

echo "==> 2/5 复制程序到 $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
SCRIPT_DIR=$(pwd)
for item in main.py config.py database.py auth.py schemas.py requirements.txt agent routers; do
    cp -r "$SCRIPT_DIR/$item" "$INSTALL_DIR/"
done

echo "==> 3/5 创建虚拟环境并安装依赖（首次约需几分钟）"
cd "$INSTALL_DIR"
if python3 -m venv venv 2>/dev/null; then
    ./venv/bin/pip install --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/
    ./venv/bin/pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
else
    echo "!! venv 不可用，回退为系统级安装"
    pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
    mkdir -p venv/bin
    ln -sf "$(command -v uvicorn)" venv/bin/uvicorn
fi

echo "==> 4/5 初始化配置文件"
# 不依赖源码中不存在的 .env.example；保留已有配置（包括符号链接）。
if [ ! -e "$INSTALL_DIR/.env" ] && [ ! -L "$INSTALL_DIR/.env" ]; then
    (
        umask 077
        set -C  # 防止检查后出现的已有文件被覆盖
        cat > "$INSTALL_DIR/.env" <<'ENV'
# 原生部署配置；启动前必须填写，切勿提交真实密钥到 Git。
# JWT_SECRET 使用 openssl rand -hex 32 在部署主机本地生成。
# 此文件由 /bin/sh 加载；值含特殊字符时需正确引用。
HOST=127.0.0.1
PORT=8080
JWT_SECRET=
WX_APPID=
WX_SECRET=
LLM_API_KEY=
ENV
    )
    echo "!! 请编辑 $INSTALL_DIR/.env 填入随机 JWT_SECRET、小程序 AppID/Secret 和大模型 API Key"
fi

echo "==> 5/5 安装启动脚本与开机自启"
cat > "$INSTALL_DIR/run.sh" <<'EOF'
#!/bin/sh
cd /opt/ka-agent
[ -f .env ] && { set -a; . ./.env; set +a; }
exec ./venv/bin/uvicorn main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8080}"
EOF
chmod +x "$INSTALL_DIR/run.sh"

cat > /etc/init.d/ka-agent <<'EOF'
#!/bin/sh /etc/rc.common

USE_PROCD=1
START=95

start_service() {
    procd_open_instance ka-agent
    procd_set_param command /opt/ka-agent/run.sh
    procd_set_param respawn
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance
}
EOF
chmod +x /etc/init.d/ka-agent
/etc/init.d/ka-agent enable

echo ""
echo "安装完成。使用方式："
echo "  1. 编辑配置：  vi /opt/ka-agent/.env"
echo "  2. 启动服务：  /etc/init.d/ka-agent start"
echo "  3. 查看日志：  logread -f | grep ka-agent"
echo "  4. 健康检查：  curl http://127.0.0.1:8080/api/health"
