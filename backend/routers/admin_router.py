"""管理后台接口：仅 ADMIN_OPENIDS 白名单用户可用。

功能：用量统计、单人/全局额度、大模型配置热更新、知识库管理。
配置修改同时写入 settings 表（持久化）并热更新到内存，无需重启容器。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException

import auth
import config
import database
import schemas

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

# 允许在线调整的配置项（key -> config 属性名）
_SETTING_KEYS = {
    "llm_base_url": "LLM_BASE_URL",
    "llm_model": "LLM_MODEL",
    "llm_api_key": "LLM_API_KEY",
    "daily_free_limit": "DAILY_FREE_LIMIT",
    "search_enabled": "SEARCH_ENABLED",
}


def _apply_to_config(key: str, value) -> None:
    """把设置热更新到内存中的 config（llm/analysis 都是运行时读取 config 属性）。"""
    attr = _SETTING_KEYS[key]
    if key == "daily_free_limit":
        setattr(config, attr, int(value))
    elif key == "search_enabled":
        setattr(config, attr, str(value).lower() != "false")
    else:
        setattr(config, attr, str(value))


def apply_settings_overrides() -> None:
    """启动时把 settings 表中已保存的覆盖值应用到 config。"""
    stored = database.all_settings()
    for key, attr in _SETTING_KEYS.items():
        db_key = attr
        if db_key in stored:
            try:
                _apply_to_config(key, stored[db_key])
            except Exception as exc:  # noqa: BLE001
                logger.warning("应用设置 %s 失败: %s", db_key, exc)


def _mask(secret: str) -> str:
    if not secret:
        return ""
    return secret[:6] + "****" + secret[-4:] if len(secret) > 12 else "****"


@router.get("/stats")
def stats(admin: dict = Depends(auth.require_admin)):
    return database.usage_stats()


@router.get("/users")
def users(admin: dict = Depends(auth.require_admin)):
    return {"items": database.list_users_admin(), "global_limit": config.DAILY_FREE_LIMIT}


@router.post("/users/{user_id}/quota")
def set_quota(user_id: int, body: schemas.AdminQuotaRequest, admin: dict = Depends(auth.require_admin)):
    if database.get_user(user_id) is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    database.set_user_quota(user_id, body.override)
    return {"user_id": user_id, "override": body.override}


@router.get("/settings")
def get_settings(admin: dict = Depends(auth.require_admin)):
    return {
        "llm_base_url": config.LLM_BASE_URL,
        "llm_model": config.LLM_MODEL,
        "llm_api_key_masked": _mask(config.LLM_API_KEY),
        "llm_api_key_set": bool(config.LLM_API_KEY),
        "daily_free_limit": config.DAILY_FREE_LIMIT,
        "search_enabled": config.SEARCH_ENABLED,
    }


@router.post("/settings")
def update_settings(body: schemas.AdminSettingsRequest, admin: dict = Depends(auth.require_admin)):
    updated = []
    for key, attr in _SETTING_KEYS.items():
        value = getattr(body, key)
        if value is None:
            continue
        if key == "llm_api_key" and "****" in str(value):
            # 防止把打码后的值写回去
            continue
        _apply_to_config(key, value)
        database.set_setting(attr, str(value).lower() if isinstance(value, bool) else str(value))
        updated.append(key)
    logger.info("管理员 %s 更新设置: %s", admin["id"], updated)
    return {"updated": updated}


@router.get("/knowledge")
def list_knowledge(admin: dict = Depends(auth.require_admin)):
    return {"items": database.list_knowledge_admin()}


@router.post("/knowledge")
def add_knowledge(body: schemas.KnowledgeDocumentRequest, admin: dict = Depends(auth.require_admin)):
    doc = database.create_knowledge_document(admin["id"], body.title, body.content, body.category, body.source_url)
    return {"id": doc["id"], "title": doc["title"]}


@router.post("/knowledge/{doc_id}/status")
def set_knowledge_status(doc_id: int, body: schemas.AdminKnowledgeStatusRequest, admin: dict = Depends(auth.require_admin)):
    database.set_knowledge_status(doc_id, body.status)
    return {"id": doc_id, "status": body.status}
