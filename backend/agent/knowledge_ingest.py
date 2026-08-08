"""知识库上传：文件解析 + 小模型提炼。

流程：上传的 Word/PDF/文本 -> 抽取纯文本 -> 用便宜档模型提炼成结构化知识条目。
提炼是上传时的一次性调用（低频），不影响主分析链路的 token 成本。
"""
from __future__ import annotations

import io
import logging
import os
import re

import config
from agent import llm, prompts

logger = logging.getLogger(__name__)

# 允许的知识分类（与提炼提示词保持一致）
CATEGORIES = ("product", "case", "competitor", "faq", "general")

# 提炼前对原文的截断上限（字符）：控制一次性 token 成本，超长文档取前部
MAX_RAW_CHARS = 20000


class IngestError(Exception):
    pass


def _ext(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lower().lstrip(".")


def _extract_docx(data: bytes) -> str:
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover
        raise IngestError("服务端缺少 python-docx 依赖") from exc
    try:
        doc = Document(io.BytesIO(data))
        parts: list[str] = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
        # 表格内容也抽出来，方案/报价常放在表格里
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text and c.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))
    except Exception as exc:  # noqa: BLE001
        raise IngestError("Word 文件解析失败，可能已损坏或不是有效的 .docx") from exc
    return "\n".join(parts)


def _extract_pdf(data: bytes) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover
        raise IngestError("服务端缺少 PyMuPDF 依赖") from exc
    text_parts: list[str] = []
    try:
        with fitz.open(stream=data, filetype="pdf") as pdf:
            for page in pdf:
                text_parts.append(page.get_text("text"))
    except Exception as exc:  # noqa: BLE001
        raise IngestError("PDF 文件解析失败，可能已损坏或不是有效的 PDF") from exc
    return "\n".join(text_parts)


def extract_text(filename: str, data: bytes) -> str:
    """按扩展名抽取纯文本。仅支持电子版文字 PDF / Word / 纯文本，不做 OCR。"""
    ext = _ext(filename)
    if ext == "docx":
        raw = _extract_docx(data)
    elif ext == "pdf":
        raw = _extract_pdf(data)
    elif ext in ("txt", "md", "markdown"):
        raw = data.decode("utf-8", errors="ignore")
    elif ext == "doc":
        raise IngestError("暂不支持旧版 .doc，请另存为 .docx 后再上传")
    else:
        raise IngestError(f"不支持的文件类型：.{ext}（目前支持 docx / pdf / txt / md）")
    raw = re.sub(r"[ \t]+\n", "\n", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw).strip()
    if len(raw) < 20:
        raise IngestError("未能从文件中抽取到有效文字（可能是扫描件/图片型 PDF，本版不支持 OCR）")
    return raw


def _normalize_category(value: str) -> str:
    v = (value or "").strip().lower()
    for c in CATEGORIES:
        if v == c or v.startswith(c):
            return c
    return "general"


def distill(filename: str, raw_text: str) -> dict:
    """调用便宜档模型把原始文本提炼为结构化知识条目。

    返回 dict：title / category / summary / content / tags / truncated / raw_chars
    """
    raw_chars = len(raw_text)
    truncated = raw_chars > MAX_RAW_CHARS
    clipped = raw_text[:MAX_RAW_CHARS]
    system = prompts.KNOWLEDGE_DISTILL_SYSTEM
    user = prompts.KNOWLEDGE_DISTILL_USER.format(filename=filename, raw_text=clipped)
    # 提炼是相对机械的清洗任务：低温 + 便宜档模型 + 不走内置联网
    result = llm.chat_json(
        system, user, temperature=0.2, enable_search=False,
        model=config.LLM_SUMMARY_MODEL or None,
    )
    title = str(result.get("title") or "").strip() or os.path.splitext(filename)[0][:60]
    category = _normalize_category(str(result.get("category") or "general"))
    summary = str(result.get("summary") or "").strip()
    content = str(result.get("content") or "").strip()
    tags = result.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in re.split(r"[,，、\s]+", tags) if t.strip()]
    tags = [str(t).strip() for t in tags if str(t).strip()][:8]
    if not content:
        raise IngestError("模型未能提炼出有效内容，请检查文档或稍后重试")
    return {
        "title": title[:200],
        "category": category,
        "summary": summary,
        "content": content,
        "tags": tags,
        "truncated": truncated,
        "raw_chars": raw_chars,
    }


def compose_stored_content(distilled: dict) -> str:
    """把提炼结果拼成最终入库正文：概览 + 正文 + 标签，一起进 FTS 便于检索命中。"""
    summary = (distilled.get("summary") or "").strip()
    content = (distilled.get("content") or "").strip()
    tags = distilled.get("tags") or []
    parts: list[str] = []
    if summary:
        parts.append(f"概览：{summary}")
    if content:
        parts.append(content)
    if tags:
        parts.append("关键词：" + "、".join(tags))
    return "\n\n".join(parts).strip()
