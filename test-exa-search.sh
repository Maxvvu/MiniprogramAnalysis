#!/bin/bash
# 测试 Exa Search 配置

set -e

SERVER="root@120.27.236.105"
KEY="~/Downloads/公众号.pem"

echo "========================================"
echo "🧪 测试 Exa Search 配置"
echo "========================================"
echo ""

# 1. 检查服务状态
echo "1️⃣  检查服务状态..."
ssh -i "$KEY" "$SERVER" "curl -s http://localhost:8080/api/health | python3 -m json.tool" || {
    echo "❌ 服务未响应"
    exit 1
}
echo ""

# 2. 检查配置
echo "2️⃣  检查搜索配置..."
ssh -i "$KEY" "$SERVER" "cd /opt/classin-ka-agent/backend && cat .env | grep -E '^SEARCH|^LLM_ENABLE'"
echo ""

# 3. 检查 API Key
echo "3️⃣  检查 Exa API Key..."
HAS_KEY=$(ssh -i "$KEY" "$SERVER" "cd /opt/classin-ka-agent/backend && grep -c '^SEARCH_API_KEY=' .env 2>/dev/null || echo 0")

if [ "$HAS_KEY" -gt 0 ]; then
    echo "✅ Exa API Key 已配置"

    # 测试搜索功能
    echo ""
    echo "4️⃣  测试搜索功能（在服务器上运行 Python 测试）..."
    ssh -i "$KEY" "$SERVER" << 'REMOTE_TEST'
cd /opt/classin-ka-agent/backend
/usr/local/bin/python3.12 << 'PYTHON_TEST'
import sys
sys.path.insert(0, '.')

from agent import searcher

# 测试搜索
print("🔍 搜索测试：新东方")
results = searcher.search_customer("新东方", "institution")

if results:
    print(f"✅ 搜索成功！获取到 {len(results)} 条结果")
    print("\n前 2 条结果：")
    for i, r in enumerate(results[:2], 1):
        print(f"\n[{i}] {r['title']}")
        print(f"    URL: {r['url']}")
        print(f"    摘要: {r['snippet'][:100]}...")
else:
    print("⚠️  搜索返回空结果（可能是 API Key 未配置或有误）")
PYTHON_TEST
REMOTE_TEST

else
    echo "⚠️  Exa API Key 未配置"
    echo ""
    echo "📝 请按照以下步骤配置："
    echo "   1. 访问 https://exa.ai 注册并获取 API Key"
    echo "   2. SSH 到服务器："
    echo "      ssh -i ~/Downloads/公众号.pem root@120.27.236.105"
    echo "   3. 编辑配置："
    echo "      vi /opt/classin-ka-agent/backend/.env"
    echo "   4. 添加："
    echo "      SEARCH_API_KEY=你的Exa_API_Key"
    echo "   5. 重启服务："
    echo "      pkill -f uvicorn && cd /opt/classin-ka-agent/backend && nohup /usr/local/bin/python3.12 /usr/local/bin/uvicorn main:app --host 0.0.0.0 --port 8080 > /tmp/ka-agent.log 2>&1 &"
fi

echo ""
echo "========================================"
echo "✅ 测试完成"
echo "========================================"
