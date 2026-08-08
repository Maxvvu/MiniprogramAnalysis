"""联网搜索：围绕客户名称多角度检索公开信息，供 LLM 分析引用。

默认使用 DuckDuckGo（ddgs 库，无需 API Key）。搜索失败不阻断流程，
LLM 会基于行业常识进行分析并在报告中标注信息来源受限。
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

import config

logger = logging.getLogger(__name__)

# 不同客户类型的搜索角度（定向覆盖工商/规模/招聘/舆情，条数与原来一致，不增加搜索用量）
QUERY_TEMPLATES = {
    "institution": [
        "{name} 企查查 天眼查 工商信息 注册资本 成立时间 分支机构",
        "{name} 融资 营收 学员规模 校区数量 加盟",
        "{name} 招聘 BOSS直聘 在招岗位 扩张 城市",
        "{name} 在线教育 直播 网课 数字化 口碑 评价 投诉",
    ],
    "teacher": [
        "{name} 老师 背景 经历 团队 招聘",
        "{name} 课程 招生 学员 口碑 评价",
        "{name} 知识付费 直播 网课 平台",
    ],
}

# 权威来源域名（命中则加权）：官方/政府/教育、工商信息、主流财经与新闻媒体
HIGH_AUTHORITY_DOMAINS = (
    "gov.cn", "edu.cn", "org.cn",
    "qcc.com", "qichacha", "tianyancha.com", "qixin.com",
    "36kr.com", "lanjinger.com", "jiemian.com", "yicai.com", "eastmoney.com",
    "cls.cn", "stcn.com", "cnstock.com", "sina.com.cn", "finance.sina",
    "people.com.cn", "xinhuanet.com", "thepaper.cn", "caixin.com",
    "iresearch.com.cn", "sensortower", "cyzone.cn", "pedaily.cn",
)

# 低质量/噪声域名（命中且与客户无关则降权或过滤）：下载站、B2B 黄页、聚合 tag 页
LOW_QUALITY_DOMAINS = (
    "b2b.", "b2b168", "china.cn", "1688.com", "makepolo", "huangye88",
    "58.com", "glodon", "download", "pcauto", "duote", "wandoujia",
    "csdn.net/download", "doc88", "docin", "book118", "taobao", "tmall",
)

# 来源权威度分层：用于给 LLM 标注每条证据的可信等级，指导其优先采信权威来源
BIZ_REGISTRY_DOMAINS = ("qcc.com", "qichacha", "tianyancha.com", "qixin.com", "gsxt.gov.cn")
OFFICIAL_DOMAINS = ("gov.cn", "edu.cn", "org.cn")
RECRUIT_DOMAINS = ("zhaopin.com", "51job.com", "liepin.com", "lagou.com", "boss", "job.com", "dajie.com")
MEDIA_DOMAINS = (
    "36kr.com", "lanjinger.com", "jiemian.com", "yicai.com", "eastmoney.com",
    "cls.cn", "stcn.com", "cnstock.com", "sina.com.cn", "finance.sina",
    "people.com.cn", "xinhuanet.com", "thepaper.cn", "caixin.com",
    "iresearch.com.cn", "cyzone.cn", "pedaily.cn",
)


def _authority_tier(url: str) -> str:
    """按域名把来源归入权威度分层，供报告与 LLM 判断证据可信度。"""
    u = (url or "").lower()
    if any(d in u for d in BIZ_REGISTRY_DOMAINS):
        return "工商信息"
    if any(d in u for d in OFFICIAL_DOMAINS):
        return "官方/政府"
    if any(d in u for d in RECRUIT_DOMAINS):
        return "招聘平台"
    if any(d in u for d in MEDIA_DOMAINS):
        return "主流媒体"
    if any(d in u for d in LOW_QUALITY_DOMAINS):
        return "低质来源"
    return "普通网页"


def _core_name(name: str) -> str:
    """去掉常见公司后缀，得到用于匹配的核心品牌词。"""
    core = re.sub(
        r"(教育科技|教育集团|科技集团|有限公司|股份有限公司|集团|教育|科技|股份|培训|学校|机构)$",
        "",
        (name or "").strip(),
    )
    return core or (name or "").strip()


def _year_of(published_at: str) -> int | None:
    m = re.search(r"(19|20)\d{2}", published_at or "")
    return int(m.group()) if m else None


def _score_result(result: dict, name: str, core: str) -> float:
    title = result.get("title", "") or ""
    snippet = result.get("snippet", "") or ""
    url = (result.get("url", "") or "").lower()
    text = title + " " + snippet
    score = 0.0

    # 实体相关性：核心名出现在标题权重最高，出现在正文次之
    if core and core in title:
        score += 3.0
    elif core and core in snippet:
        score += 1.5
    if name and name != core and name in text:
        score += 0.5

    # 来源权威度
    if any(d in url for d in HIGH_AUTHORITY_DOMAINS):
        score += 2.0
    if any(d in url for d in LOW_QUALITY_DOMAINS):
        score -= 3.0

    # 时效性
    year = _year_of(result.get("published_at", ""))
    if year:
        cur = datetime.now().year
        if year >= cur - 1:
            score += 1.5
        elif year >= cur - 3:
            score += 0.5
        else:
            score -= 0.5

    # provider 自带相关性分数（如 tavily 的 0~1 score）
    raw = result.get("score")
    if isinstance(raw, (int, float)):
        score += float(raw) * 2.0

    return score


def _rank_and_filter(results: list[dict], name: str, top_k: int | None = None) -> list[dict]:
    """对搜索结果按相关性/权威度/时效性排序，剔除明显无关的噪声，返回 top_k 条。"""
    if not results:
        return results
    if top_k is None:
        top_k = config.SEARCH_TOP_K

    core = _core_name(name)
    scored = [(_score_result(r, name, core), r) for r in results]

    def _mentions(r: dict) -> bool:
        text = (r.get("title", "") or "") + " " + (r.get("snippet", "") or "")
        return (core and core in text) or (name and name in text)

    def _low_quality(r: dict) -> bool:
        url = (r.get("url", "") or "").lower()
        return any(d in url for d in LOW_QUALITY_DOMAINS)

    # 实体消歧：既不提及客户、又落在低质量域名的结果直接丢弃
    kept = [(s, r) for s, r in scored if _mentions(r) or not _low_quality(r)]
    if len(kept) < 3:  # 过滤过狠会饿死分析，回退到全量排序
        kept = scored

    kept.sort(key=lambda x: x[0], reverse=True)
    ranked = [r for _, r in kept[:top_k]]
    for r in ranked:
        r["authority"] = _authority_tier(r.get("url", ""))
    logger.info("搜索结果排序: 原始 %s 条 → 保留 %s 条", len(results), len(ranked))
    return ranked


def search_customer(
    name: str,
    customer_type: str = "institution",
    keywords: list[str] | None = None,
) -> list[dict]:
    """返回 [{title, url, snippet}] 形式的搜索结果列表。搜索后端由 SEARCH_PROVIDER 决定。

    keywords：screen 阶段由模型针对该客户生成的精准搜索关键词。若提供，优先用其构造查询，
    固定模板降为补充，从而提升搜索命中的精准度。
    """
    if not config.SEARCH_ENABLED or config.SEARCH_PROVIDER == "off":
        return []

    queries: list[str] = []
    seen_queries: set[str] = set()

    def _add_query(q: str) -> None:
        q = q.strip()
        if q and q not in seen_queries:
            seen_queries.add(q)
            queries.append(q)

    # 1) 优先：模型生成的精准关键词（未包含公司名的自动补上公司名）
    for kw in keywords or []:
        kw = (kw or "").strip()
        if not kw:
            continue
        _add_query(kw if name in kw else f"{name} {kw}")

    # 2) 补充：固定模板查询，保证基础覆盖面
    templates = QUERY_TEMPLATES.get(customer_type, QUERY_TEMPLATES["institution"])
    for tpl in templates:
        _add_query(tpl.format(name=name))

    provider = config.SEARCH_PROVIDER
    results: list[dict] = []
    seen_urls: set[str] = set()
    for query in queries:
        try:
            if provider == "http":
                items = _search_http(query)
            elif provider == "exa":
                items = _search_exa(query)
            elif provider == "tavily":
                items = _search_tavily(query)
            elif provider == "bocha":
                items = _search_bocha(query)
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
    return _rank_and_filter(results, name)


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


def _search_tavily(query: str) -> list[dict]:
    """Tavily AI 检索：返回清洗后的正文与相关性分数，对中英文实体均友好。"""
    import httpx

    if not config.SEARCH_API_KEY:
        logger.warning("SEARCH_PROVIDER=tavily 但未配置 SEARCH_API_KEY，跳过")
        return []

    url = "https://api.tavily.com/search"
    payload = {
        "api_key": config.SEARCH_API_KEY,
        "query": query,
        "search_depth": "advanced",  # 深度检索，返回更完整正文
        "max_results": config.SEARCH_MAX_RESULTS,
        "include_answer": False,
        "include_raw_content": False,
    }
    with httpx.Client(timeout=30) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

    out: list[dict] = []
    for item in data.get("results", []):
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": (item.get("content") or "")[:1000],
                "score": item.get("score"),
                "published_at": item.get("published_date") or "",
            }
        )
    return out


def _search_bocha(query: str) -> list[dict]:
    """博查 Web Search：国内 AI 搜索，对中文教培实体覆盖好。"""
    import httpx

    if not config.SEARCH_API_KEY:
        logger.warning("SEARCH_PROVIDER=bocha 但未配置 SEARCH_API_KEY，跳过")
        return []

    url = "https://api.bochaai.com/v1/web-search"
    headers = {
        "Authorization": f"Bearer {config.SEARCH_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "summary": True,  # 返回长摘要正文
        "count": config.SEARCH_MAX_RESULTS,
    }
    with httpx.Client(timeout=30) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    # 博查返回形如 {"data": {"webPages": {"value": [...]}}}
    pages = (
        data.get("data", {}).get("webPages", {}).get("value", [])
        if isinstance(data, dict)
        else []
    )
    out: list[dict] = []
    for item in pages:
        if not isinstance(item, dict):
            continue
        snippet = item.get("summary") or item.get("snippet") or ""
        out.append(
            {
                "title": item.get("name", ""),
                "url": item.get("url", ""),
                "snippet": snippet[:1000],
                "published_at": item.get("datePublished") or item.get("dateLastCrawled") or "",
            }
        )
    return out


def truncate_text(text: str, max_chars: int) -> str:
    """按字符上限截断，尽量在换行/句号边界收尾，避免半句；超出加省略标记。"""
    if max_chars <= 0 or not text or len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    for sep in ("\n", "。", "！", "？", "; ", ". "):
        idx = cut.rfind(sep)
        if idx >= max_chars * 0.6:  # 断点太靠前就不用，免得丢太多内容
            cut = cut[: idx + len(sep)]
            break
    return cut.rstrip() + " …（已截断）"


def format_search_context(results: list[dict], limit: int | None = None) -> str:
    """把搜索结果拼成供 LLM 阅读的上下文文本。

    单条摘要按 SEARCH_SNIPPET_MAX_CHARS 截断，汇总再按 SEARCH_CONTEXT_MAX_CHARS 收口，
    控制喂给（便宜档）模型的体量，省 token、降噪声、防超时。
    """
    if not results:
        return "（未获取到联网搜索信息，请基于教培行业常识分析，并在报告中注明信息有限）"
    if limit is None:
        limit = config.SEARCH_TOP_K
    lines = []
    for i, r in enumerate(results[:limit], 1):
        date = r.get("published_at") or ""
        tier = r.get("authority") or ""
        snippet = truncate_text(r.get("snippet", "") or "", config.SEARCH_SNIPPET_MAX_CHARS)
        meta = f"来源: {r['url']}"
        if tier:
            meta += f"｜可信度: {tier}"
        if date:
            meta += f"｜发布时间: {date}"
        lines.append(f"[{i}] {r['title']}\n{snippet}\n{meta}")
    return truncate_text("\n\n".join(lines), config.SEARCH_CONTEXT_MAX_CHARS)
