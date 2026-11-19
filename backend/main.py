"""FastAPI 入口。启动：uvicorn main:app --host 127.0.0.1 --port 8080"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config
import database
from routers import admin_router, analysis_router, auth_router, knowledge_web_router, memory_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

database.init_db()
admin_router.apply_settings_overrides()
_stale = database.fail_stale_tasks()
if _stale:
    logging.getLogger(__name__).info("启动清理：标记 %s 个残留任务为中断", _stale)

app = FastAPI(title="ClassIn KA 客户分析 Agent", version="1.0.0")

# 便于本地联调；微信小程序正式请求不受 CORS 影响
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(analysis_router.router)
app.include_router(memory_router.router)
app.include_router(admin_router.router)
app.include_router(knowledge_web_router.router)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "wx_configured": bool(config.WX_APPID and config.WX_SECRET),
        "llm_configured": bool(config.LLM_API_KEY),
        "model": config.LLM_MODEL,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=config.HOST, port=config.PORT)
