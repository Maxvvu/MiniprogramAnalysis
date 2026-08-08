#!/usr/bin/env python3
"""
DuckDuckGo 搜索（通过 Xray 代理）
支持智能重试和错误处理
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 代理配置
PROXY = "http://127.0.0.1:10808"

def create_session():
    """创建带重试机制的 Session"""
    session = requests.Session()

    # 配置重试策略
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # 设置代理
    session.proxies = {
        'http': PROXY,
        'https': PROXY
    }

    # 设置 User-Agent
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })

    return session

def search_duckduckgo(query: str, max_results: int = 5):
    """
    使用 DuckDuckGo HTML 搜索
    """
    session = create_session()

    try:
        # DuckDuckGo HTML 搜索 URL
        url = f"https://html.duckduckgo.com/html/?q={quote(query)}"

        # 发送请求
        response = session.get(url, timeout=15, verify=True)
        response.raise_for_status()

        # 解析 HTML
        soup = BeautifulSoup(response.text, 'html.parser')

        # 提取搜索结果
        results = []
        for result_div in soup.find_all('div', class_='result', limit=max_results):
            title_tag = result_div.find('a', class_='result__a')
            snippet_tag = result_div.find('a', class_='result__snippet')

            if title_tag:
                title = title_tag.get_text(strip=True)
                url = title_tag.get('href', '')
                snippet = snippet_tag.get_text(strip=True) if snippet_tag else ''

                results.append({
                    'title': title,
                    'url': url,
                    'snippet': snippet
                })

        return results

    except requests.exceptions.SSLError as e:
        print(f"SSL 错误（可能是节点不支持 HTTPS）: {e}")
        return None
    except requests.exceptions.Timeout:
        print("请求超时")
        return None
    except Exception as e:
        print(f"搜索失败: {e}")
        return None
    finally:
        session.close()

def search_google_via_proxy(query: str, max_results: int = 5):
    """
    尝试使用 Google 搜索（备选方案）
    """
    session = create_session()

    try:
        url = f"https://www.google.com/search?q={quote(query)}"
        response = session.get(url, timeout=15, verify=True)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        results = []

        # Google 搜索结果的 CSS 类可能会变化，这里用简单的解析
        for g in soup.find_all('div', class_='g', limit=max_results):
            title_tag = g.find('h3')
            link_tag = g.find('a')
            snippet_tag = g.find('div', class_='VwiC3b')

            if title_tag and link_tag:
                title = title_tag.get_text(strip=True)
                url = link_tag.get('href', '')
                snippet = snippet_tag.get_text(strip=True) if snippet_tag else ''

                results.append({
                    'title': title,
                    'url': url,
                    'snippet': snippet
                })

        return results

    except Exception as e:
        print(f"Google 搜索失败: {e}")
        return None
    finally:
        session.close()

def search_with_fallback(query: str, max_results: int = 5):
    """
    智能搜索：先尝试 DuckDuckGo，失败则尝试 Google
    """
    print(f"🔍 搜索: {query}")
    print("-" * 60)

    # 尝试 DuckDuckGo
    print("尝试 DuckDuckGo...")
    results = search_duckduckgo(query, max_results)

    if results:
        print(f"✅ DuckDuckGo 成功，找到 {len(results)} 条结果")
        return results

    # 尝试 Google
    print("DuckDuckGo 失败，尝试 Google...")
    results = search_google_via_proxy(query, max_results)

    if results:
        print(f"✅ Google 成功，找到 {len(results)} 条结果")
        return results

    print("❌ 所有搜索引擎都失败")
    return []

if __name__ == "__main__":
    print("=" * 60)
    print("测试 DuckDuckGo 搜索（通过 Xray 代理）")
    print("=" * 60)
    print()

    # 测试搜索
    results = search_with_fallback("新东方教育", max_results=3)

    if results:
        print()
        print("=" * 60)
        print("搜索结果:")
        print("=" * 60)
        for i, result in enumerate(results, 1):
            print(f"\n{i}. {result['title']}")
            print(f"   URL: {result['url']}")
            print(f"   摘要: {result['snippet'][:100]}...")
    else:
        print("\n❌ 搜索失败")
