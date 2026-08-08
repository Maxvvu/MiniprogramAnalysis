"""联网搜索：围绕客户名称多角度检索公开信息，供 LLM 分析引用。

默认使用 DuckDuckGo（ddgs 库，无需 API Key）。搜索失败不阻断流程，
LLM 会基于行业常识进行分析并在报告中标注信息来源受限。
"""
import logging

import config

logger = logging.getLogger(__name__)

# 不同客户类型的搜索角度
QUERY_TEMPLATES = {
    "institution": [
        "{name} 教培机构 简介 规模",
        "{name} 融资 营收 招生",
        "{name} 校区 扩张 加盟",
        "{name} 在线教育 直播 网课",
    ],
    "teacher": [
        "{name} 老师 培训 讲师 简介",
        "{name} 课程 招生 学员",
        "{name} 知识付费 直播 网课",
    ],
}


def search_customer(name: str, customer_type: str = "institution") -> list[dict]:
    """返回 [{title, url, snippet}] 形式的搜索结果列表。搜索后端由 SEARCH_PROVIDER 决定。"""
    if not config.SEARCH_ENABLED or config.SEARCH_PROVIDER == "off":
        return []

    templates = QUERY_TEMPLATES.get(customer_type, QUERY_TEMPLATES["institution"])
    queries = [tpl.format(name=name) for tpl in templates]

    provider = config.SEARCH_PROVIDER
    results: list[dict] = []
    seen_urls: set[str] = set()
    for query in queries:
        try:
            if provider == "http":
                items = _search_http(query)
            elif provider == "exa":
                items = _search_exa(query)
            else:
                items = _search_ddgs(query)
        except Exception as exc:  # noqa: BLE001 单条查询失败不影响整体
            logger.warning("搜索失败 query=%s err=%s", query, exc)
            continue
        for item in items:
            url = item.get("url") or ""
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            results.append(item)
    return results


def _search_ddgs(query: str) -> list[dict]:
    """DuckDuckGo 搜索（无需 Key，境外网络可用）。"""
    try:
        from ddgs import DDGS
    except ImportError:
        logger.warning("ddgs 未安装，跳过联网搜索")
        return []
    out: list[dict] = []
    with DDGS() as ddgs:
        for item in ddgs.text(query, max_results=config.SEARCH_MAX_RESULTS):
            out.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("href") or item.get("url") or "",
                    "snippet": item.get("body") or item.get("snippet") or "",
                }
            )
    return out


def _search_http(query: str) -> list[dict]:
    """通用付费搜索 HTTP API 适配器。

    约定：GET SEARCH_API_URL?q=<query>，带 Authorization Bearer SEARCH_API_KEY。
    兼容常见返回形状：results / organic / items / data，字段 title、url|link、snippet|body|content。
    若所选 API 形状不同，仅需在此函数内补充一种解析，无需改业务代码。
    """
    import httpx

    if not config.SEARCH_API_URL:
        logger.warning("SEARCH_PROVIDER=http 但未配置 SEARCH_API_URL，跳过")
        return []
    headers = {}
    if config.SEARCH_API_KEY:
        headers["Authorization"] = f"Bearer {config.SEARCH_API_KEY}"
    with httpx.Client(timeout=20) as client:
        resp = client.get(config.SEARCH_API_URL, params={"q": query}, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    raw = None
    for key in ("results", "organic", "items", "data"):
        if isinstance(data, dict) and isinstance(data.get(key), list):
            raw = data[key]
            break
    if raw is None:
        return []
    out: list[dict] = []
    for item in raw[: config.SEARCH_MAX_RESULTS]:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "title": str(item.get("title", "")),
                "url": str(item.get("url") or item.get("link") or ""),
                "snippet": str(item.get("snippet") or item.get("body") or item.get("content") or ""),
            }
        )
    return out


def _search_exa(query: str) -> list[dict]:
    """Exa AI Search（专为 AI 优化的搜索引擎，免费 1000 次/月）。"""
    import httpx

    if not config.SEARCH_API_KEY:
        logger.warning("SEARCH_PROVIDER=exa 但未配置 SEARCH_API_KEY，跳过")
        return []

    url = "https://api.exa.ai/search"
    headers = {
        "x-api-key": config.SEARCH_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "numResults": config.SEARCH_MAX_RESULTS,
        "contents": {"text": {"maxCharacters": 500}},
        "useAutoprompt": True,  # 让 Exa 优化搜索查询
    }

    with httpx.Client(timeout=20) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    out: list[dict] = []
    for item in data.get("results", []):
        text_content = item.get("text", "")
        # 如果没有 text，用 title 作为 snippet
        snippet = text_content if text_content else item.get("title", "")
        out.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": snippet[:500],  # 限制长度
        })
    return out


def format_search_context(results: list[dict], limit: int = 30) -> str:
    """把搜索结果拼成供 LLM 阅读的上下文文本。"""
    if not results:
        return "（未获取到联网搜索信息，请基于教培行业常识分析，并在报告中注明信息有限）"
    lines = []
    for i, r in enumerate(results[:limit], 1):
        lines.append(f"[{i}] {r['title']}\n{r['snippet']}\n来源: {r['url']}")
    return "\n\n".join(lines)
