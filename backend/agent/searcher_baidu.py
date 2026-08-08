"""
百度搜索 API 集成方案
官方文档：https://ai.baidu.com/tech/websearch
"""

import requests
from typing import List, Dict

def search_baidu(query: str, max_results: int = 5) -> List[Dict]:
    """
    使用百度搜索 API
    需要申请百度智能云账号：https://console.bce.baidu.com/
    """
    # 百度搜索 API 配置
    API_KEY = "your_baidu_api_key"
    SECRET_KEY = "your_baidu_secret_key"

    # 1. 获取 access_token
    token_url = "https://aip.baidubce.com/oauth/2.0/token"
    token_params = {
        "grant_type": "client_credentials",
        "client_id": API_KEY,
        "client_secret": SECRET_KEY
    }

    token_response = requests.post(token_url, params=token_params)
    access_token = token_response.json().get("access_token")

    # 2. 调用搜索 API
    search_url = "https://aip.baidubce.com/rpc/2.0/nlp/v1/news_summary"
    headers = {"Content-Type": "application/json"}
    params = {"access_token": access_token}
    payload = {
        "query": query,
        "max_summary_len": 200
    }

    response = requests.post(search_url, headers=headers, params=params, json=payload)

    # 解析结果
    results = []
    if response.status_code == 200:
        data = response.json()
        # 根据实际返回格式解析
        results = data.get("results", [])[:max_results]

    return results


# 百度还有更简单的网页搜索爬虫方案（免费）
def search_baidu_html(query: str, max_results: int = 5) -> List[Dict]:
    """
    直接爬取百度搜索结果页（完全免费，但需要处理反爬虫）
    """
    from bs4 import BeautifulSoup
    from urllib.parse import quote

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Cookie': 'BAIDUID=xxx'  # 可选：添加 Cookie 提高稳定性
    }

    url = f"https://www.baidu.com/s?wd={quote(query)}"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        results = []

        # 解析百度搜索结果
        for item in soup.select('.result')[:max_results]:
            title_elem = item.select_one('h3 a')
            snippet_elem = item.select_one('.c-abstract')

            if title_elem:
                results.append({
                    'title': title_elem.get_text(strip=True),
                    'url': title_elem.get('href', ''),
                    'snippet': snippet_elem.get_text(strip=True) if snippet_elem else ''
                })

        return results

    except Exception as e:
        print(f"百度搜索失败: {e}")
        return []


if __name__ == "__main__":
    # 测试百度搜索（爬虫方式，完全免费）
    results = search_baidu_html("新东方教育")
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['title']}")
        print(f"   {r['url']}")
        print()
