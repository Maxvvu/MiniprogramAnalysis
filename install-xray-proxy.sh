#!/bin/bash
# 在阿里云服务器上安装并配置 Xray 代理

set -e

echo "========================================"
echo "🪜 安装 Xray 代理客户端"
echo "========================================"

# 1. 安装 Xray
echo "📥 安装 Xray..."
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install

# 2. 下载订阅配置
echo "📥 下载订阅配置..."
SUB_URL="https://d7b12d59-21aa-9561-087f-89c834ac7fe8.372372.xyz/api/v1/client/subscribe?token=e99c185b01429293fe416e6882dc2522"
curl -sL "$SUB_URL" | base64 -d > /tmp/proxy_nodes.txt

# 3. 选择一个新加坡节点（最快）
FIRST_NODE=$(grep "vless://.*sg001" /tmp/proxy_nodes.txt | head -1)

if [ -z "$FIRST_NODE" ]; then
    echo "❌ 未找到可用节点"
    exit 1
fi

echo "✅ 找到节点: $(echo $FIRST_NODE | grep -oP '#.*' | head -1)"

# 4. 解析节点参数
UUID=$(echo $FIRST_NODE | grep -oP '(?<=vless://)[^@]+')
SERVER=$(echo $FIRST_NODE | grep -oP '(?<=@)[^:]+')
PORT=$(echo $FIRST_NODE | grep -oP '(?<=:)\d+(?=\?)')
SERVICE_NAME=$(echo $FIRST_NODE | grep -oP '(?<=serviceName=)[^&]+')
SNI=$(echo $FIRST_NODE | grep -oP '(?<=sni=)[^&]+')
PBK=$(echo $FIRST_NODE | grep -oP '(?<=pbk=)[^&]+')
SID=$(echo $FIRST_NODE | grep -oP '(?<=sid=)[^&#]+')

# 5. 生成 Xray 配置文件
cat > /usr/local/etc/xray/config.json << EOF
{
  "log": {
    "loglevel": "warning"
  },
  "inbounds": [
    {
      "port": 10809,
      "protocol": "socks",
      "settings": {
        "auth": "noauth",
        "udp": true
      },
      "sniffing": {
        "enabled": true,
        "destOverride": ["http", "tls"]
      }
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
        "vnext": [
          {
            "address": "$SERVER",
            "port": $PORT,
            "users": [
              {
                "id": "$UUID",
                "encryption": "none",
                "flow": ""
              }
            ]
          }
        ]
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
        "grpcSettings": {
          "serviceName": "$SERVICE_NAME"
        }
      }
    }
  ]
}
EOF

echo ""
echo "✅ Xray 配置完成！"
echo "   - SOCKS5: 127.0.0.1:10809"
echo "   - HTTP: 127.0.0.1:10808"
echo ""

# 6. 启动 Xray
echo "🚀 启动 Xray 服务..."
systemctl enable xray
systemctl restart xray
sleep 3

if systemctl is-active --quiet xray; then
    echo "✅ Xray 服务运行正常"
else
    echo "❌ Xray 启动失败，查看日志："
    journalctl -u xray -n 20 --no-pager
    exit 1
fi

# 7. 测试代理
echo ""
echo "🧪 测试代理连接..."
if curl -x socks5h://127.0.0.1:10809 -s --connect-timeout 10 https://www.google.com > /dev/null; then
    echo "✅ 代理测试成功！可以访问 Google"
else
    echo "⚠️  代理测试失败，可能需要等待几秒钟"
fi

echo ""
echo "========================================"
echo "✅ Xray 安装完成！"
echo "========================================"
echo ""
echo "📌 使用方式："
echo "   1. 全局代理（所有命令）："
echo "      export http_proxy=http://127.0.0.1:10808"
echo "      export https_proxy=http://127.0.0.1:10808"
echo ""
echo "   2. 单次使用："
echo "      curl -x http://127.0.0.1:10808 https://www.google.com"
echo ""
echo "   3. Python 程序（ddgs 库）会自动使用环境变量代理"
echo ""
