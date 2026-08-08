#!/bin/bash
# 快速安装 Xray 代理（手动下载二进制）

set -e

echo "========================================"
echo "🪜 快速安装 Xray 代理"
echo "========================================"

# 1. 下载 Xray 二进制（使用国内镜像）
echo "📥 下载 Xray 二进制文件..."
cd /tmp
if [ ! -f xray ]; then
    wget -q --show-progress https://github.com/XTLS/Xray-core/releases/download/v1.8.23/Xray-linux-64.zip -O xray.zip || \
    curl -L -o xray.zip https://github.com/XTLS/Xray-core/releases/download/v1.8.23/Xray-linux-64.zip

    unzip -o xray.zip
    chmod +x xray
    mv xray /usr/local/bin/
    echo "✅ Xray 安装成功"
else
    echo "✅ Xray 已存在"
fi

# 2. 创建配置目录
mkdir -p /usr/local/etc/xray

# 3. 下载订阅并解析
echo "📥 下载代理节点..."
SUB_URL="https://d7b12d59-21aa-9561-087f-89c834ac7fe8.372372.xyz/api/v1/client/subscribe?token=e99c185b01429293fe416e6882dc2522"
curl -sL "$SUB_URL" | base64 -d > /tmp/nodes.txt

# 选择第一个新加坡节点
NODE=$(grep "vless://.*sg001" /tmp/nodes.txt | head -1)

# 解析节点信息
UUID=$(echo "$NODE" | sed 's/vless:\/\/\([^@]*\).*/\1/')
SERVER=$(echo "$NODE" | sed 's/.*@\([^:]*\):.*/\1/')
PORT=$(echo "$NODE" | sed 's/.*:\([0-9]*\)?.*/\1/')
SERVICE_NAME=$(echo "$NODE" | grep -oP 'serviceName=\K[^&]*')
SNI=$(echo "$NODE" | grep -oP 'sni=\K[^&]*')
PBK=$(echo "$NODE" | grep -oP 'pbk=\K[^&]*')
SID=$(echo "$NODE" | grep -oP 'sid=\K[^&#]*')

echo "✅ 使用节点: $SERVER:$PORT"

# 4. 生成配置文件
cat > /usr/local/etc/xray/config.json << EOF
{
  "log": {"loglevel": "warning"},
  "inbounds": [
    {
      "port": 10809,
      "protocol": "socks",
      "settings": {"auth": "noauth", "udp": true}
    },
    {
      "port": 10808,
      "protocol": "http",
      "settings": {}
    }
  ],
  "outbounds": [
    {
      "protocol": "vless",
      "settings": {
        "vnext": [{
          "address": "$SERVER",
          "port": $PORT,
          "users": [{"id": "$UUID", "encryption": "none"}]
        }]
      },
      "streamSettings": {
        "network": "grpc",
        "security": "reality",
        "realitySettings": {
          "serverName": "$SNI",
          "publicKey": "$PBK",
          "shortId": "$SID",
          "fingerprint": "firefox"
        },
        "grpcSettings": {"serviceName": "$SERVICE_NAME"}
      }
    }
  ]
}
EOF

# 5. 创建 systemd 服务
cat > /etc/systemd/system/xray.service << 'EOF'
[Unit]
Description=Xray Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/xray run -config /usr/local/etc/xray/config.json
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

# 6. 启动服务
systemctl daemon-reload
systemctl enable xray
systemctl restart xray
sleep 2

# 7. 检查状态
if systemctl is-active --quiet xray; then
    echo "✅ Xray 运行正常"

    # 测试连接
    echo "🧪 测试代理..."
    if curl -x socks5h://127.0.0.1:10809 -s --connect-timeout 5 https://www.google.com > /dev/null 2>&1; then
        echo "✅ 代理测试成功！"
    else
        echo "⚠️  等待连接稳定..."
    fi
else
    echo "❌ Xray 启动失败"
    journalctl -u xray -n 20 --no-pager
    exit 1
fi

echo ""
echo "========================================"
echo "✅ 安装完成！"
echo "========================================"
echo "SOCKS5: 127.0.0.1:10809"
echo "HTTP:   127.0.0.1:10808"
