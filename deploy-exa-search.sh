#!/bin/bash
# 部署脚本：将本地修改同步到阿里云服务器，并配置 Exa 搜索

set -e

SERVER="root@120.27.236.105"
KEY="~/Downloads/公众号.pem"
REMOTE_DIR="/opt/classin-ka-agent"

echo "========================================"
echo "🚀 部署 Exa Search 到阿里云服务器"
echo "========================================"

# 1. 上传修改后的 searcher.py
echo "📤 上传 searcher.py..."
scp -i "$KEY" backend/agent/searcher.py "$SERVER:$REMOTE_DIR/backend/agent/"

# 2. 上传 .env.example
echo "📤 上传 .env.example..."
scp -i "$KEY" backend/.env.example "$SERVER:$REMOTE_DIR/backend/"

# 3. 在服务器上配置 Exa
echo "⚙️  配置 Exa Search..."
ssh -i "$KEY" "$SERVER" << 'REMOTE_SCRIPT'
cd /opt/classin-ka-agent/backend

# 检查是否已配置 SEARCH_PROVIDER
if grep -q "^SEARCH_PROVIDER=exa" .env 2>/dev/null; then
    echo "✅ Exa 已配置"
else
    echo "📝 更新 .env 配置..."

    # 启用搜索
    sed -i 's/^SEARCH_ENABLED=.*/SEARCH_ENABLED=true/' .env
    sed -i 's/^SEARCH_PROVIDER=.*/SEARCH_PROVIDER=exa/' .env

    # 关闭模型内置联网（省钱）
    sed -i 's/^LLM_ENABLE_SEARCH=.*/LLM_ENABLE_SEARCH=false/' .env

    echo ""
    echo "⚠️  需要手动配置 Exa API Key："
    echo "   1. 访问 https://exa.ai 注册并获取 API Key"
    echo "   2. 编辑 /opt/classin-ka-agent/backend/.env"
    echo "   3. 添加：SEARCH_API_KEY=你的Exa_API_Key"
    echo ""
fi

# 4. 重启服务
echo "🔄 重启服务..."
pkill -f "uvicorn main:app" || true
sleep 2
cd /opt/classin-ka-agent/backend
nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 8080 > /tmp/ka-agent.log 2>&1 &
sleep 3

# 检查服务状态
if pgrep -f "uvicorn main:app" > /dev/null; then
    echo "✅ 服务已启动"
    echo "📋 日志: tail -f /tmp/ka-agent.log"
else
    echo "❌ 服务启动失败，查看日志："
    tail -20 /tmp/ka-agent.log
fi
REMOTE_SCRIPT

echo ""
echo "========================================"
echo "✅ 部署完成！"
echo "========================================"
echo ""
echo "📌 下一步："
echo "   1. 注册 Exa AI: https://exa.ai"
echo "   2. 获取 API Key（免费 1000 次/月）"
echo "   3. SSH 到服务器："
echo "      ssh -i ~/Downloads/公众号.pem root@120.27.236.105"
echo "   4. 编辑配置："
echo "      vi /opt/classin-ka-agent/backend/.env"
echo "      添加: SEARCH_API_KEY=你的Key"
echo "   5. 重启服务："
echo "      pkill -f uvicorn && cd /opt/classin-ka-agent/backend && nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 8080 > /tmp/ka-agent.log 2>&1 &"
echo ""
