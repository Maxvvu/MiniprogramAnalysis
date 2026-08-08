#!/usr/bin/env python3
"""
测试 V2Ray 代理搜索
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import quote

# V2Ray 代理地址
PROXY = "http://127.0.0.1:10809"

def test_v2ray_proxy():
    """测试 V2Ray 代理"""
    proxies = {
        'http': PROXY,
        'https': PROXY
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    print("=" * 60)
    print("测试 V2Ray 代理")
    print("=" * 60)
    print()

    # 1. 测试基础连接
    print("1. 测试 Google 连接...")
    try:
        r = requests.get('https://www.google.com', proxies=proxies, headers=headers, timeout=15)
        print(f"   ✅ 成功 (状态码: {r.status_code})")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
        return False

    # 2. 测试 DuckDuckGo 搜索
    print("\n2. 测试 DuckDuckGo 搜索...")
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote('新东方教育')}"
        r = requests.get(url, proxies=proxies, headers=headers, timeout=15)
        print(f"   ✅ 成功 (状态码: {r.status_code})")

        soup = BeautifulSoup(r.text, 'html.parser')
        results = soup.find_all('div', class_='result', limit=3)

        if results:
            print(f"   ✅ 找到 {len(results)} 条结果")
            print("\n   搜索结果:")
            for i, result in enumerate(results, 1):
                title_tag = result.find('a', class_='result__a')
                if title_tag:
                    print(f"   {i}. {title_tag.get_text(strip=True)[:60]}")
            return True
        else:
            print("   ⚠️  未找到搜索结果")
            return False

    except Exception as e:
        print(f"   ❌ 失败: {e}")
        return False

if __name__ == "__main__":
    success = test_v2ray_proxy()

    print("\n" + "=" * 60)
    if success:
        print("🎉 V2Ray 代理测试成功！")
        print("=" * 60)
        print("\n✅ 可以使用 V2Ray 代理进行搜索")
        print("✅ 代理地址: http://127.0.0.1:10809")
    else:
        print("❌ V2Ray 代理测试失败")
        print("=" * 60)
