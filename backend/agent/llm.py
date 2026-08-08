"""大模型调用：OpenAI 兼容协议客户端。

默认对接阿里云百炼 DashScope，通过 .env 可切换 DeepSeek、OpenAI 等任意兼容接口：
    LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
"""
import json
import logging
import re
import time

import httpx

import config

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


def chat(system: str, user: str, temperature: float = 0.4, retries: int = 3) -> str:
    """单轮对话，返回模型文本输出。"""
    if not config.LLM_API_KEY:
        raise LLMError("未配置 LLM_API_KEY，请在 backend/.env 中填入大模型 API Key")
    url = f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": config.LLM_MODEL,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if config.LLM_MAX_TOKENS > 0:
        payload["max_tokens"] = config.LLM_MAX_TOKENS
    if config.LLM_ENABLE_SEARCH:
        payload["enable_search"] = True
    headers = {"Authorization": f"Bearer {config.LLM_API_KEY}"}
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


def chat_json(system: str, user: str, temperature: float = 0.4, attempts: int = 3) -> dict:
    """要求模型输出 JSON 并稳健解析；单次输出偶发截断/坏格式时自动重采样。"""
    prompt = user + "\n\n请只输出 JSON，不要包含任何解释文字。"
    last_text = ""
    for _ in range(attempts):
        last_text = chat(system, prompt, temperature)
        parsed = _parse_json(last_text)
        if parsed is not None:
            return parsed
        # 解析失败：稍等后重采样一次（输出具有随机性，重试通常能得到完整 JSON）
        time.sleep(1)
    raise LLMError(f"模型输出不是合法 JSON: {last_text[:300]}")
