"""Worker 进程：轮询任务队列并执行分析任务。

与 Web 服务分离运行，支持：
- 任务持久化（SQLite 队列，重启不丢失）
- 真实取消（每个阶段前检查 cancelled 状态）
- 断点续跑（从 stage_index 恢复）
"""
import logging
import signal
import sys
import time

import database
from agent import pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [worker] %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

POLL_INTERVAL = 2  # 轮询间隔（秒）
_shutdown = False


def _handle_shutdown(signum, frame):
    global _shutdown
    logger.info("收到信号 %s，准备退出…", signum)
    _shutdown = True


signal.signal(signal.SIGINT, _handle_shutdown)
signal.signal(signal.SIGTERM, _handle_shutdown)


def main():
    logger.info("Worker 启动，轮询间隔 %ds", POLL_INTERVAL)
    database.init_db()
    database.fail_stale_tasks()  # 清理上次残留

    while not _shutdown:
        task_id = database.dequeue_task()
        if task_id is None:
            time.sleep(POLL_INTERVAL)
            continue

        logger.info("取出任务 task_id=%d", task_id)
        try:
            pipeline.run_task(task_id)
        except Exception:
            logger.exception("task_id=%d worker 异常", task_id)
            database.update_task(task_id, status="failed", stage="", error="Worker 内部异常")

    logger.info("Worker 已退出")


if __name__ == "__main__":
    main()
