#!/bin/bash
# 部署脚本：同步删除功能到阿里云服务器

set -e

SERVER="root@120.27.236.105"
KEY="~/Downloads/公众号.pem"
REMOTE_DIR="/opt/classin-ka-agent"

echo "========================================"
echo "🚀 部署删除功能到阿里云服务器"
echo "========================================"

# 1. 上传后端文件
echo "📤 上传后端文件..."
scp -i "$KEY" backend/database.py "$SERVER:$REMOTE_DIR/backend/"
scp -i "$KEY" backend/routers/analysis_router.py "$SERVER:$REMOTE_DIR/backend/routers/"

# 2. 上传小程序文件
echo "📤 上传小程序文件..."
scp -i "$KEY" miniprogram/pages/history/history.js "$SERVER:$REMOTE_DIR/miniprogram/pages/history/"
scp -i "$KEY" miniprogram/pages/history/history.wxml "$SERVER:$REMOTE_DIR/miniprogram/pages/history/"
scp -i "$KEY" miniprogram/pages/history/history.wxss "$SERVER:$REMOTE_DIR/miniprogram/pages/history/"

# 3. 重启后端服务
echo "🔄 重启后端服务..."
ssh -i "$KEY" "$SERVER" << 'REMOTE_SCRIPT'
cd /opt/classin-ka-agent/backend

# 重启服务
pkill -f "uvicorn main:app" || true
sleep 2
nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 8080 > /tmp/ka-agent.log 2>&1 &
sleep 3

# 检查服务状态
if pgrep -f "uvicorn main:app" > /dev/null; then
    echo "✅ 后端服务已启动"
else
    echo "❌ 后端服务启动失败，查看日志："
    tail -20 /tmp/ka-agent.log
    exit 1
fi
REMOTE_SCRIPT

echo ""
echo "========================================"
echo "✅ 部署完成！"
echo "========================================"
echo ""
echo "📌 新增功能："
echo "   - 删除单个分析记录"
echo "   - 清空所有分析记录"
echo "   - 长按记录显示删除选项"
echo ""
echo "📋 查看日志: ssh -i ~/Downloads/公众号.pem root@120.27.236.105 'tail -f /tmp/ka-agent.log'"
echo ""
