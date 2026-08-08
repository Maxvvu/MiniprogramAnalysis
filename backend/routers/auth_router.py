"""登录与用户信息接口。"""
from fastapi import APIRouter, Depends, HTTPException

import auth
import database
import schemas

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/wx-login", response_model=schemas.TokenResponse)
async def wx_login(body: schemas.WxLoginRequest):
    """小程序 wx.login 的 code 换取应用会话 Token。"""
    try:
        openid = await auth.wx_code2session(body.code)
    except auth.WxLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    user = database.upsert_user(openid, body.nickname)
    return schemas.TokenResponse(
        token=auth.create_token(user["id"]),
        user_id=user["id"],
        nickname=user["nickname"],
        is_admin=auth.is_admin(user),
    )


@router.get("/me")
def me(user: dict = Depends(auth.get_current_user)):
    filled = bool((user.get("real_name") or "").strip() or (user.get("phone") or "").strip())
    return {
        "user_id": user["id"],
        "nickname": user["nickname"],
        "is_admin": auth.is_admin(user),
        "real_name": user.get("real_name") or "",
        "phone": user.get("phone") or "",
        "need_profile": not filled and not user.get("profile_dismissed"),
    }


@router.post("/profile")
def save_profile(body: schemas.ProfileRequest, user: dict = Depends(auth.get_current_user)):
    import re

    if not re.fullmatch(r"1\d{10}", body.phone):
        raise HTTPException(status_code=400, detail="手机号格式不正确")
    database.update_user_profile(user["id"], body.name, body.phone)
    return {"ok": True}


@router.post("/profile-skip")
def skip_profile(user: dict = Depends(auth.get_current_user)):
    database.dismiss_profile(user["id"])
    return {"ok": True}
