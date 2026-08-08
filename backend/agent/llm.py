"""大模型调用：OpenAI 兼容协议客户端。

默认对接阿里云百炼 DashScope，通过 .env 可切换 DeepSeek、OpenAI 等任意兼容接口：
    LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
"""
from __future__ import annotations

import json
import logging
import re
import time

import httpx

import config

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


def chat(system: str, user: str, temperature: float = 0.4, retries: int = 3,
         enable_search: bool | None = None, model: str | None = None,
         base_url: str | None = None, api_key: str | None = None) -> str:
    """单轮对话，返回模型文本输出。

    enable_search：是否启用模型内置联网搜索。None 时用 config.LLM_ENABLE_SEARCH；
    对已注入自有搜索上下文的阶段（profile/analyze）可显式传 False，避免重复联网导致的高延迟/超时。
    model：显式指定模型名，用于知识库提炼等场景切换到便宜档；留空则用 config.LLM_MODEL。
    base_url / api_key：显式指定服务商端点与密钥，用于切换到第三方中转等；留空则用 config 主配置。
    """
    key = (api_key or "").strip() or config.LLM_API_KEY
    if not key:
        raise LLMError("未配置 LLM_API_KEY，请在 backend/.env 中填入大模型 API Key")
    base = (base_url or "").strip() or config.LLM_BASE_URL
    url = f"{base.rstrip('/')}/chat/completions"
    payload = {
        "model": (model or "").strip() or config.LLM_MODEL,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if config.LLM_MAX_TOKENS > 0:
        payload["max_tokens"] = config.LLM_MAX_TOKENS
    use_search = config.LLM_ENABLE_SEARCH if enable_search is None else enable_search
    if use_search:
        payload["enable_search"] = True
    headers = {"Authorization": f"Bearer {key}"}
    last_err = ""
    for attempt in range(retries + 1):
        try:
            with httpx.Client(timeout=config.LLM_TIMEOUT) as client:
                resp = client.post(url, json=payload, headers=headers)
                # 429/404/5xx 都视为可重试：中转组模型路由经常瞬时不可用
                if resp.status_code in (429, 404) or resp.status_code >= 500:
                    last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    time.sleep(3 * (attempt + 1))
                    continue
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
        except httpx.HTTPError as exc:
            last_err = str(exc)
            time.sleep(2 * (attempt + 1))
    raise LLMError(f"大模型调用失败: {last_err}")


def _repair_json(text: str) -> str:
    """修复常见截断/笔误产物：去掉 } 或 ] 前的尾逗号。"""
    return re.sub(r",\s*([}\]])", r"\1", text)


def _parse_json(text: str):
    """尝试多种清洗策略解析模型输出，成功返回 dict，失败返回 None。"""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    candidates = [cleaned, _repair_json(cleaned)]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        sub = cleaned[start : end + 1]
        candidates += [sub, _repair_json(sub)]
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue
    return None


def chat_json(system: str, user: str, temperature: float = 0.4, attempts: int = 3,
              enable_search: bool | None = None, model: str | None = None,
              base_url: str | None = None, api_key: str | None = None) -> dict:
    """要求模型输出 JSON 并稳健解析；单次输出偶发截断/坏格式时自动重采样。"""
    prompt = user + "\n\n请只输出 JSON，不要包含任何解释文字。"
    last_text = ""
    for _ in range(attempts):
        last_text = chat(system, prompt, temperature, enable_search=enable_search,
                         model=model, base_url=base_url, api_key=api_key)
        parsed = _parse_json(last_text)
        if parsed is not None:
            return parsed
        # 解析失败：稍等后重采样一次（输出具有随机性，重试通常能得到完整 JSON）
        time.sleep(1)
    raise LLMError(f"模型输出不是合法 JSON: {last_text[:300]}")


def cheap_provider_enabled() -> bool:
    """是否配置了 profile 等降档阶段专用的便宜档/第三方中转。"""
    return bool(config.LLM_CHEAP_API_KEY and config.LLM_CHEAP_MODEL)


def chat_json_cheap_first(system: str, user: str, temperature: float = 0.4,
                          attempts: int = 3, enable_search: bool | None = None) -> dict:
    """降档阶段专用：优先走便宜中转，失败（含重试仍失败/坏 JSON）自动回退主模型。

    便宜中转不稳定时，chat() 内置的 429/404/5xx 重试先兜一层瞬时抖动；
    彻底不可用才回退到 config 主模型（当前稳定的百炼 qwen），保证任务成功率不下降。
    """
    if cheap_provider_enabled():
        try:
            result = chat_json(
                system, user, temperature, attempts,
                enable_search=enable_search,
                model=config.LLM_CHEAP_MODEL,
                base_url=config.LLM_CHEAP_BASE_URL or None,
                api_key=config.LLM_CHEAP_API_KEY,
            )
            logger.info("降档阶段使用便宜中转成功: model=%s", config.LLM_CHEAP_MODEL)
            return result
        except LLMError as exc:
            logger.warning("便宜中转不可用，回退主模型: %s", exc)
    return chat_json(system, user, temperature, attempts, enable_search=enable_search)
