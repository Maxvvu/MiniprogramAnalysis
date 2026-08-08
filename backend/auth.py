"""微信小程序登录与 JWT 会话管理。"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import config
import database

_bearer = HTTPBearer(auto_error=False)


class WxLoginError(Exception):
    pass


async def wx_code2session(code: str) -> str:
    """用 wx.login 的 code 换取 openid。"""
    if not config.WX_APPID or not config.WX_SECRET:
        raise WxLoginError("服务端未配置 WX_APPID / WX_SECRET")
    params = {
        "appid": config.WX_APPID,
        "secret": config.WX_SECRET,
        "js_code": code,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(config.WX_LOGIN_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
    if "openid" not in data:
        raise WxLoginError(f"微信登录失败: {data.get('errmsg', data)}")
    return data["openid"]


def create_token(user_id: int) -> str:
    payload = {
        "uid": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=config.JWT_EXPIRE_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALG)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    """FastAPI 依赖：从 Bearer Token 解析当前用户。"""
    if credentials is None:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = jwt.decode(credentials.credentials, config.JWT_SECRET, algorithms=[config.JWT_ALG])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    user = database.get_user(int(payload["uid"]))
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def is_admin(user: dict) -> bool:
    return user.get("openid") in config.ADMIN_OPENIDS


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """FastAPI 依赖：仅白名单管理员可用。"""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="无管理权限")
    return user
