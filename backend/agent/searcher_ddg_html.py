"""
使用 requests + BeautifulSoup 直接爬取 DuckDuckGo 搜索结果
无需代理，无需安装 duckduckgo-search 库
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import quote

def search_duckduckgo_html(query: str, max_results: int = 5) -> list[dict]:
    """
    通过 HTML 页面爬取 DuckDuckGo 搜索结果（无需代理）
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    # DuckDuckGo HTML 搜索（国内可访问）
    url = f"https://html.duckduckgo.com/html/?q={quote(query)}"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        results = []

        # 解析搜索结果
        for result in soup.select('.result')[:max_results]:
            title_elem = result.select_one('.result__a')
            snippet_elem = result.select_one('.result__snippet')

            if title_elem:
                results.append({
                    'title': title_elem.get_text(strip=True),
                    'url': title_elem.get('href', ''),
                    'snippet': snippet_elem.get_text(strip=True) if snippet_elem else ''
                })

        return results

    except Exception as e:
        print(f"搜索失败: {e}")
        return []


# 测试
if __name__ == "__main__":
    results = search_duckduckgo_html("新东方教育")
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['title']}")
        print(f"   {r['url']}")
        print(f"   {r['snippet'][:80]}...")
        print()
