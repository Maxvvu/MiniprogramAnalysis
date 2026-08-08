"""SQLite 存储层：任务、客户长期记忆与轻量知识库。"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import re

import config

_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock, _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                openid      TEXT UNIQUE NOT NULL,
                nickname    TEXT DEFAULT '',
                created_at  INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL,
                customer_name  TEXT NOT NULL,
                customer_type  TEXT NOT NULL DEFAULT 'institution',
                extra_notes    TEXT DEFAULT '',
                status         TEXT NOT NULL DEFAULT 'pending',
                stage          TEXT DEFAULT '',
                report_json    TEXT DEFAULT '',
                report_md      TEXT DEFAULT '',
                error          TEXT DEFAULT '',
                created_at     INTEGER NOT NULL,
                updated_at     INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                customer_type TEXT NOT NULL DEFAULT 'institution',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(user_id, normalized_name, customer_type),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                snippet TEXT NOT NULL DEFAULT '',
                captured_at INTEGER NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            );
            CREATE TABLE IF NOT EXISTS customer_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                task_id INTEGER,
                fact TEXT NOT NULL,
                fact_kind TEXT NOT NULL DEFAULT 'candidate',
                confidence TEXT NOT NULL DEFAULT 'medium',
                source_urls TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'candidate',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id),
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            );
            CREATE TABLE IF NOT EXISTS customer_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS customer_memory_summaries (
                customer_id INTEGER PRIMARY KEY,
                summary TEXT NOT NULL DEFAULT '',
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );
            CREATE TABLE IF NOT EXISTS knowledge_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                source_url TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                created_by INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (created_by) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                FOREIGN KEY (document_id) REFERENCES knowledge_documents(id)
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts
                USING fts5(content, tokenize='unicode61');
            CREATE TABLE IF NOT EXISTS settings (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            );
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
        if "customer_id" not in columns:
            conn.execute("ALTER TABLE tasks ADD COLUMN customer_id INTEGER")
        user_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        if "quota_override" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN quota_override INTEGER")
        if "real_name" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN real_name TEXT DEFAULT ''")
        if "phone" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN phone TEXT DEFAULT ''")
        if "profile_dismissed" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN profile_dismissed INTEGER DEFAULT 0")


# ---------- users ----------

def upsert_user(openid: str, nickname: str = "") -> dict:
    now = int(time.time())
    with _lock, _conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE openid = ?", (openid,)).fetchone()
        if row:
            return dict(row)
        cur = conn.execute(
            "INSERT INTO users (openid, nickname, created_at) VALUES (?, ?, ?)",
            (openid, nickname, now),
        )
        row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


def get_user(user_id: int) -> dict | None:
    with _lock, _conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def update_user_profile(user_id: int, real_name: str, phone: str) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "UPDATE users SET real_name = ?, phone = ?, profile_dismissed = 1 WHERE id = ?",
            (real_name.strip(), phone.strip(), user_id),
        )


def dismiss_profile(user_id: int) -> None:
    with _lock, _conn() as conn:
        conn.execute("UPDATE users SET profile_dismissed = 1 WHERE id = ?", (user_id,))


# ---------- tasks ----------

def create_task(user_id: int, customer_name: str, customer_type: str, extra_notes: str) -> dict:
    now = int(time.time())
    customer = get_or_create_customer(user_id, customer_name, customer_type)
    with _lock, _conn() as conn:
        cur = conn.execute(
            """INSERT INTO tasks
               (user_id, customer_id, customer_name, customer_type, extra_notes, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (user_id, customer["id"], customer_name,
             customer_type, extra_notes, now, now),
        )
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


def update_task(task_id: int, **fields) -> None:
    fields["updated_at"] = int(time.time())
    if "report_json" in fields and not isinstance(fields["report_json"], str):
        fields["report_json"] = json.dumps(fields["report_json"], ensure_ascii=False)
    keys = ", ".join(f"{k} = ?" for k in fields)
    with _lock, _conn() as conn:
        conn.execute(f"UPDATE tasks SET {keys} WHERE id = ?", (*fields.values(), task_id))


def get_task(task_id: int) -> dict | None:
    with _lock, _conn() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None


def list_tasks(user_id: int, limit: int = 50) -> list[dict]:
    with _lock, _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def _today_start_ts() -> int:
    """今天 0 点（北京时间 UTC+8）的 unix 时间戳。"""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone(timedelta(hours=8)))
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(midnight.timestamp())


def count_tasks_today(user_id: int) -> int:
    """统计用户今天（北京时间）已提交的分析任务数，用于每日免费次数限制。"""
    start = _today_start_ts()
    with _lock, _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE user_id = ? AND created_at >= ?",
            (user_id, start),
        ).fetchone()
        return int(row["n"])


def cancel_task(task_id: int, user_id: int) -> bool:
    """用户取消自己尚未完成的任务，返回是否成功。"""
    now = int(time.time())
    with _lock, _conn() as conn:
        cur = conn.execute(
            "UPDATE tasks SET status = 'failed', error = '已手动取消', updated_at = ? "
            "WHERE id = ? AND user_id = ? AND status IN ('pending', 'running')",
            (now, task_id, user_id),
        )
        return cur.rowcount > 0


def fail_stale_tasks() -> int:
    """启动时把残留的 pending/running 任务标记为中断（后台线程不跨重启存活）。"""
    now = int(time.time())
    with _lock, _conn() as conn:
        cur = conn.execute(
            "UPDATE tasks SET status = 'failed', error = '服务重启，任务中断', updated_at = ? "
            "WHERE status IN ('pending', 'running')",
            (now,),
        )
        return cur.rowcount


def delete_task(task_id: int, user_id: int) -> bool:
    """删除指定任务（含关联 sources），返回是否成功。"""
    with _lock, _conn() as conn:
        cur = conn.execute(
            "DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id)
        )
        if cur.rowcount > 0:
            conn.execute("DELETE FROM sources WHERE task_id = ?", (task_id,))
            return True
        return False


def clear_all_tasks(user_id: int) -> int:
    """清空用户的所有分析任务（含关联 sources），返回删除数量。"""
    with _lock, _conn() as conn:
        task_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM tasks WHERE user_id = ?", (user_id,)
        ).fetchall()]
        if not task_ids:
            return 0
        placeholders = ",".join("?" * len(task_ids))
        conn.execute(f"DELETE FROM sources WHERE task_id IN ({placeholders})", task_ids)
        cur = conn.execute("DELETE FROM tasks WHERE user_id = ?", (user_id,))
        return cur.rowcount


def find_recent_done_task(user_id: int, customer_name: str, customer_type: str, since_ts: int):
    """同一用户近期对同一客户的成功分析（用于结果复用、省 token），无则返回 None。"""
    normalized = _normalize_name(customer_name)
    with _lock, _conn() as conn:
        # 直接通过 customer_name 匹配，避免依赖 tasks 表中不存在的 customer_id 字段
        row = conn.execute(
            """SELECT * FROM tasks
               WHERE user_id = ?
                 AND LOWER(REPLACE(REPLACE(customer_name, ' ', ''), '　', '')) = ?
                 AND customer_type = ?
                 AND status = 'done'
                 AND created_at >= ?
               ORDER BY id DESC LIMIT 1""",
            (user_id, normalized, customer_type, since_ts),
        ).fetchone()
        return dict(row) if row else None


def find_task_by_customer(user_id: int, customer_name: str, customer_type: str):
    """查找同一用户同一客户的最近一条任务（任意状态），用于去重更新而非新建。"""
    normalized = _normalize_name(customer_name)
    with _lock, _conn() as conn:
        row = conn.execute(
            """SELECT * FROM tasks
               WHERE user_id = ?
                 AND LOWER(REPLACE(REPLACE(customer_name, ' ', ''), '　', '')) = ?
                 AND customer_type = ?
               ORDER BY id DESC LIMIT 1""",
            (user_id, normalized, customer_type),
        ).fetchone()
        return dict(row) if row else None


def reset_task_for_rerun(task_id: int, extra_notes: str = "") -> dict:
    """将任务重置为 pending 以便重新分析（保留 id，更新内容而非新建条目）。"""
    now = int(time.time())
    with _lock, _conn() as conn:
        conn.execute(
            """UPDATE tasks SET status='pending', stage='', error='',
               report_json='', report_md='', extra_notes=?, updated_at=?
               WHERE id=?""",
            (extra_notes, now, task_id),
        )
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row)


# ---------- 客户长期记忆 ----------

def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", name).lower()


def get_or_create_customer(user_id: int, name: str, customer_type: str) -> dict:
    now = int(time.time())
    normalized = _normalize_name(name)
    with _lock, _conn() as conn:
        row = conn.execute(
            "SELECT * FROM customers WHERE user_id = ? AND normalized_name = ? AND customer_type = ?",
            (user_id, normalized, customer_type),
        ).fetchone()
        if row:
            conn.execute("UPDATE customers SET updated_at = ? WHERE id = ?", (now, row["id"]))
            return dict(row)
        cur = conn.execute(
            """INSERT INTO customers (user_id, name, normalized_name, customer_type, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, name, normalized, customer_type, now, now),
        )
        return dict(conn.execute("SELECT * FROM customers WHERE id = ?", (cur.lastrowid,)).fetchone())


def get_customer(customer_id: int, user_id: int) -> dict | None:
    with _lock, _conn() as conn:
        row = conn.execute("SELECT * FROM customers WHERE id = ? AND user_id = ?", (customer_id, user_id)).fetchone()
        return dict(row) if row else None


def list_customers(user_id: int, limit: int = 100) -> list[dict]:
    with _lock, _conn() as conn:
        rows = conn.execute(
            """SELECT c.*, s.summary, s.updated_at AS memory_updated_at
               FROM customers c LEFT JOIN customer_memory_summaries s ON s.customer_id = c.id
               WHERE c.user_id = ? ORDER BY c.updated_at DESC LIMIT ?""", (user_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def save_sources(task_id: int, results: list[dict]) -> list[dict]:
    now = int(time.time())
    with _lock, _conn() as conn:
        conn.execute("DELETE FROM sources WHERE task_id = ?", (task_id,))
        for result in results:
            conn.execute("INSERT INTO sources (task_id, title, url, snippet, captured_at) VALUES (?, ?, ?, ?, ?)",
                         (task_id, result.get("title", ""), result.get("url", ""), result.get("snippet", ""), now))
        return [dict(r) for r in conn.execute("SELECT * FROM sources WHERE task_id = ?", (task_id,)).fetchall()]


def add_profile_facts(customer_id: int, task_id: int, facts: list, confidence: str, source_urls: list[str]) -> None:
    now = int(time.time())
    with _lock, _conn() as conn:
        for item in facts:
            fact = item.get("fact", "") if isinstance(item, dict) else str(item)
            urls = item.get("source_urls", source_urls) if isinstance(item, dict) else source_urls
            if not fact.strip():
                continue
            exists = conn.execute(
                "SELECT 1 FROM customer_facts WHERE customer_id = ? AND fact = ? AND status != 'discarded'",
                (customer_id, fact.strip()),
            ).fetchone()
            if not exists:
                conn.execute(
                    """INSERT INTO customer_facts
                       (customer_id, task_id, fact, confidence, source_urls, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (customer_id, task_id, fact.strip(), confidence, json.dumps(urls, ensure_ascii=False), now, now),
                )


def add_customer_note(customer_id: int, user_id: int, content: str) -> dict:
    now = int(time.time())
    with _lock, _conn() as conn:
        cur = conn.execute("INSERT INTO customer_notes (customer_id, user_id, content, created_at) VALUES (?, ?, ?, ?)",
                           (customer_id, user_id, content.strip(), now))
        conn.execute("UPDATE customers SET updated_at = ? WHERE id = ?", (now, customer_id))
        return dict(conn.execute("SELECT * FROM customer_notes WHERE id = ?", (cur.lastrowid,)).fetchone())


def get_customer_memory(customer_id: int, limit: int = 12) -> dict:
    with _lock, _conn() as conn:
        summary = conn.execute("SELECT summary, updated_at FROM customer_memory_summaries WHERE customer_id = ?", (customer_id,)).fetchone()
        facts = conn.execute("SELECT * FROM customer_facts WHERE customer_id = ? AND status != 'discarded' ORDER BY updated_at DESC LIMIT ?", (customer_id, limit)).fetchall()
        notes = conn.execute("SELECT * FROM customer_notes WHERE customer_id = ? ORDER BY created_at DESC LIMIT ?", (customer_id, limit)).fetchall()
        return {"summary": dict(summary) if summary else {"summary": "", "updated_at": None},
                "facts": [dict(r) for r in facts], "notes": [dict(r) for r in notes]}


def upsert_memory_summary(customer_id: int, summary: str) -> None:
    now = int(time.time())
    with _lock, _conn() as conn:
        conn.execute("""INSERT INTO customer_memory_summaries (customer_id, summary, updated_at) VALUES (?, ?, ?)
                      ON CONFLICT(customer_id) DO UPDATE SET summary = excluded.summary, updated_at = excluded.updated_at""",
                     (customer_id, summary.strip(), now))


# ---------- 轻量知识库（SQLite FTS5） ----------

def _chunk_text(text: str, size: int = 600, overlap: int = 100) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    return [text[i:i + size] for i in range(0, len(text), size - overlap) if text[i:i + size]]


def _segment(text: str) -> list[str]:
    """中文分词。优先 jieba（检索更准），缺失时退化为连续字串。"""
    try:
        import jieba

        words = jieba.cut_for_search(text)
    except ImportError:
        words = re.findall(r"[\w一-鿿]+", text)
    seen = []
    for w in words:
        w = w.strip()
        if w and re.search(r"[\w一-鿿]", w) and w not in seen:
            seen.append(w)
    return seen


def create_knowledge_document(user_id: int, title: str, content: str, category: str, source_url: str = "") -> dict:
    now = int(time.time())
    with _lock, _conn() as conn:
        cur = conn.execute("""INSERT INTO knowledge_documents
                           (title, content, category, source_url, created_by, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                           (title.strip(), content.strip(), category.strip() or "general", source_url.strip(), user_id, now, now))
        document_id = cur.lastrowid
        for index, chunk in enumerate(_chunk_text(content)):
            chunk_id = conn.execute("INSERT INTO knowledge_chunks (document_id, chunk_index, content) VALUES (?, ?, ?)",
                                    (document_id, index, chunk)).lastrowid
            conn.execute("INSERT INTO knowledge_chunks_fts (rowid, content) VALUES (?, ?)",
                         (chunk_id, " ".join(_segment(chunk))))
        return dict(conn.execute("SELECT * FROM knowledge_documents WHERE id = ?", (document_id,)).fetchone())


def search_knowledge(query: str, limit: int = 6) -> list[dict]:
    terms = _segment(query) or re.findall(r"[\w\u4e00-\u9fff]+", query)
    if not terms:
        return []
    match = " OR ".join(terms[:12])
    with _lock, _conn() as conn:
        try:
            rows = conn.execute(
                """SELECT c.content, d.id AS document_id, d.title, d.category, d.source_url,
                          bm25(knowledge_chunks_fts) AS score
                   FROM knowledge_chunks_fts JOIN knowledge_chunks c ON c.id = knowledge_chunks_fts.rowid
                   JOIN knowledge_documents d ON d.id = c.document_id
                   WHERE knowledge_chunks_fts MATCH ? AND d.status = 'active'
                   ORDER BY score LIMIT ?""", (match, limit)
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        if not rows:
            clauses = " OR ".join("d.title LIKE ? OR c.content LIKE ?" for _ in terms[:12])
            params = [value for term in terms[:12] for value in (f"%{term}%", f"%{term}%")]
            rows = conn.execute(
                """SELECT c.content, d.id AS document_id, d.title, d.category, d.source_url, 0 AS score
                   FROM knowledge_chunks c JOIN knowledge_documents d ON d.id = c.document_id
                   WHERE d.status = 'active' AND (""" + clauses + ") ORDER BY d.updated_at DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
        return [dict(r) for r in rows]


# ---------- 运行时设置（管理后台可调，持久化到 DB） ----------

def get_setting(key: str) -> str | None:
    with _lock, _conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def set_setting(key: str, value: str) -> None:
    now = int(time.time())
    with _lock, _conn() as conn:
        conn.execute(
            """INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
            (key, value, now),
        )


def all_settings() -> dict:
    with _lock, _conn() as conn:
        return {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM settings")}


# ---------- 管理后台 ----------

def set_user_quota(user_id: int, override: int | None) -> None:
    with _lock, _conn() as conn:
        conn.execute("UPDATE users SET quota_override = ? WHERE id = ?", (override, user_id))


def list_users_admin() -> list[dict]:
    start = _today_start_ts()
    with _lock, _conn() as conn:
        rows = conn.execute(
            """SELECT u.id, u.openid, u.nickname, u.quota_override, u.created_at,
                (SELECT COUNT(*) FROM tasks t WHERE t.user_id = u.id) AS total_tasks,
                (SELECT COUNT(*) FROM tasks t WHERE t.user_id = u.id AND t.status = 'done') AS done_tasks,
                (SELECT COUNT(*) FROM tasks t WHERE t.user_id = u.id AND t.status = 'failed') AS failed_tasks,
                (SELECT COUNT(*) FROM tasks t WHERE t.user_id = u.id AND t.created_at >= ?) AS today_tasks
               FROM users u ORDER BY u.id""",
            (start,),
        ).fetchall()
        return [dict(r) for r in rows]


def usage_stats() -> dict:
    start = _today_start_ts()
    with _lock, _conn() as conn:
        total_users = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        total_tasks = conn.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()["n"]
        done = conn.execute("SELECT COUNT(*) AS n FROM tasks WHERE status = 'done'").fetchone()["n"]
        failed = conn.execute("SELECT COUNT(*) AS n FROM tasks WHERE status = 'failed'").fetchone()["n"]
        today = conn.execute("SELECT COUNT(*) AS n FROM tasks WHERE created_at >= ?", (start,)).fetchone()["n"]
        return {
            "total_users": total_users,
            "total_tasks": total_tasks,
            "done_tasks": done,
            "failed_tasks": failed,
            "today_tasks": today,
        }


def list_knowledge_admin(limit: int = 100) -> list[dict]:
    with _lock, _conn() as conn:
        rows = conn.execute(
            "SELECT id, title, category, source_url, status, created_by, created_at, length(content) AS chars "
            "FROM knowledge_documents ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def set_knowledge_status(doc_id: int, status: str) -> None:
    with _lock, _conn() as conn:
        conn.execute("UPDATE knowledge_documents SET status = ?, updated_at = ? WHERE id = ?",
                     (status, int(time.time()), doc_id))
