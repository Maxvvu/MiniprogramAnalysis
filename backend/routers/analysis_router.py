"""客户分析任务接口：提交、查询、列表、报告下载。"""
import json
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse

import auth
import config
import database
import schemas
from agent import pipeline

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


def _task_view(task: dict) -> dict:
    """对外输出的任务视图：不暴露内部字段。"""
    view = {
        "id": task["id"],
        "customer_name": task["customer_name"],
        "customer_type": task["customer_type"],
        "status": task["status"],
        "stage": task["stage"],
        "error": task["error"],
        "created_at": task["created_at"],
        "updated_at": task["updated_at"],
    }
    if task["status"] == "done" and task["report_json"]:
        report = json.loads(task["report_json"])
        view["analysis"] = report["analysis"]
        view["profile"] = report.get("profile", {})
        view["report_md"] = task["report_md"]
        view["docx_name"] = report.get("docx_name", "")
        view["solution"] = report.get("solution", {})
        view["solution_md"] = report.get("solution_md", "")
    return view


def _effective_limit(user: dict) -> int:
    """单人额度覆盖优先，否则用全局 DAILY_FREE_LIMIT。"""
    override = user.get("quota_override")
    return override if override is not None else config.DAILY_FREE_LIMIT


def _cache_since_ts() -> int:
    return int(time.time()) - config.CACHE_TTL_DAYS * 86400


@router.get("/recent")
def recent_analysis(
    customer_name: str,
    customer_type: str = "institution",
    user: dict = Depends(auth.get_current_user),
):
    """查询该用户近期是否已有此客户的成功分析（用于提示复用、省 token）。"""
    task = database.find_recent_done_task(user["id"], customer_name, customer_type, _cache_since_ts())
    if not task:
        return {"task_id": None}
    days_ago = max((int(time.time()) - task["created_at"]) // 86400, 0)
    return {"task_id": task["id"], "days_ago": days_ago}


@router.get("/quota")
def get_quota(user: dict = Depends(auth.get_current_user)):
    """当前用户今日免费分析额度（按北京时间自然日重置）。"""
    used = database.count_tasks_today(user["id"])
    limit = _effective_limit(user)
    remaining = max(limit - used, 0) if limit > 0 else None
    return {"limit": limit, "used": used, "remaining": remaining}


@router.post("")
def create_analysis(
    body: schemas.AnalysisRequest,
    background: BackgroundTasks,
    user: dict = Depends(auth.get_current_user),
):
    # 结果复用：同一用户近期已分析过同一客户且未强制重跑 → 直接返回旧报告，不耗额度不烧 token
    if not body.force:
        cached = database.find_recent_done_task(
            user["id"], body.customer_name, body.customer_type, _cache_since_ts()
        )
        if cached:
            return {"task_id": cached["id"], "status": cached["status"], "cached": True}
    limit = _effective_limit(user)
    if limit > 0:
        used = database.count_tasks_today(user["id"])
        if used >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"今日免费分析次数已用完（{limit} 次/天），明天 0 点后重置",
            )
    # 去重：同一客户已有任务则复用原条目重跑（避免分析记录出现重复条目）
    existing = database.find_task_by_customer(user["id"], body.customer_name, body.customer_type)
    if existing:
        task = database.reset_task_for_rerun(existing["id"], body.extra_notes)
    else:
        task = database.create_task(user["id"], body.customer_name, body.customer_type, body.extra_notes)
    background.add_task(pipeline.run_analysis, task["id"])
    return {"task_id": task["id"], "status": task["status"]}


@router.get("")
def list_analysis(user: dict = Depends(auth.get_current_user)):
    tasks = database.list_tasks(user["id"])
    return {"items": [_task_view(t) for t in tasks]}


@router.get("/{task_id}")
def get_analysis(task_id: int, user: dict = Depends(auth.get_current_user)):
    task = database.get_task(task_id)
    if task is None or task["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _task_view(task)


@router.post("/{task_id}/cancel")
def cancel_analysis(task_id: int, user: dict = Depends(auth.get_current_user)):
    task = database.get_task(task_id)
    if task is None or task["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not database.cancel_task(task_id, user["id"]):
        raise HTTPException(status_code=400, detail="该任务已完成或已取消")
    return {"ok": True}


@router.post("/clear")
def clear_all_analysis(user: dict = Depends(auth.get_current_user)):
    """清空当前用户的所有分析记录。"""
    count = database.clear_all_tasks(user["id"])
    return {"ok": True, "count": count}


@router.delete("/{task_id}")
def delete_analysis(task_id: int, user: dict = Depends(auth.get_current_user)):
    """删除指定分析记录。"""
    task = database.get_task(task_id)
    if task is None or task["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not database.delete_task(task_id, user["id"]):
        raise HTTPException(status_code=400, detail="删除失败")
    return {"ok": True}


@router.get("/{task_id}/docx")
def download_docx(task_id: int, user: dict = Depends(auth.get_current_user)):
    task = database.get_task(task_id)
    if task is None or task["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] != "done" or not task["report_json"]:
        raise HTTPException(status_code=400, detail="报告尚未生成完成")
    docx_name = json.loads(task["report_json"]).get("docx_name", "")
    path = config.REPORT_DIR / docx_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="报告文件不存在")
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=docx_name)


@router.get("/{task_id}/solution-docx")
def download_solution_docx(task_id: int, user: dict = Depends(auth.get_current_user)):
    task = database.get_task(task_id)
    if task is None or task["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] != "done" or not task["report_json"]:
        raise HTTPException(status_code=400, detail="解决方案尚未生成完成")
    solution = json.loads(task["report_json"]).get("solution", {})
    docx_name = solution.get("docx_name", "")
    path = config.REPORT_DIR / docx_name
    if not docx_name or not path.exists():
        raise HTTPException(status_code=404, detail="解决方案文件不存在")
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=docx_name)
