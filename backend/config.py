"""全局配置：优先读取环境变量，其次读取 backend/.env 文件。"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


# ---------- 服务 ----------
HOST = _env("HOST", "127.0.0.1")
PORT = int(_env("PORT", "8080"))
# 数据目录：SQLite 数据库与生成的报告存放位置
DATA_DIR = Path(_env("DATA_DIR", str(BASE_DIR.parent / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_DIR = DATA_DIR / "db"
DB_DIR.mkdir(exist_ok=True)
REPORT_DIR = DATA_DIR / "reports"
REPORT_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "ka_agent.db"

# ---------- 微信小程序 ----------
WX_APPID = _env("WX_APPID")
WX_SECRET = _env("WX_SECRET")
WX_LOGIN_URL = "https://api.weixin.qq.com/sns/jscode2session"

# ---------- JWT 会话 ----------
JWT_SECRET = _env("JWT_SECRET")
if len(JWT_SECRET.encode("utf-8")) < 32:
    raise RuntimeError(
        "JWT_SECRET must be explicitly configured with at least 32 bytes; "
        "generate a random secret with: openssl rand -hex 32"
    )
JWT_ALG = "HS256"
JWT_EXPIRE_DAYS = int(_env("JWT_EXPIRE_DAYS", "30"))

# ---------- 大模型（OpenAI 兼容接口） ----------
# 默认使用阿里云百炼 DashScope 的 OpenAI 兼容模式，可切换为 DeepSeek / OpenAI 等
LLM_BASE_URL = _env("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
LLM_API_KEY = _env("LLM_API_KEY")
LLM_MODEL = _env("LLM_MODEL", "qwen-max")
LLM_TIMEOUT = int(_env("LLM_TIMEOUT", "180"))
# 请求的输出 token 上限（0 = 不发送该参数）。部分中转默认上限很小会截断长 JSON，
# 遇到"模型输出不是合法 JSON"时可设为 4096 等较大值。
LLM_MAX_TOKENS = int(_env("LLM_MAX_TOKENS", "0"))
# 模型内置联网搜索（仅通用 qwen 等支持 enable_search 的模型可用；coder 系会报 400，默认关）
LLM_ENABLE_SEARCH = _env("LLM_ENABLE_SEARCH", "false").lower() != "false"
# 知识库上传提炼专用的"小模型/便宜档"：上传是低频操作，用便宜模型清洗提炼即可，
# 不影响主分析质量。留空则回退到 LLM_MODEL。
LLM_SUMMARY_MODEL = _env("LLM_SUMMARY_MODEL", "")
# profile 阶段降档专用的"便宜档/第三方中转"（OpenAI 兼容）。用于把整理搜索结果成客户档案
# 这类读多写少的阶段切到更便宜的模型省钱。三项需成套配置（base_url 可留空表示复用主端点）；
# API_KEY 与 MODEL 任一为空则视为未启用，profile 仍走主模型。
# 中转不稳定无妨：profile 走 chat_json_cheap_first，中转失败会自动回退主模型，不影响成功率。
LLM_CHEAP_BASE_URL = _env("LLM_CHEAP_BASE_URL", "")
LLM_CHEAP_API_KEY = _env("LLM_CHEAP_API_KEY", "")
LLM_CHEAP_MODEL = _env("LLM_CHEAP_MODEL", "")

# ---------- 联网搜索 ----------
SEARCH_ENABLED = _env("SEARCH_ENABLED", "true").lower() != "false"
SEARCH_MAX_RESULTS = int(_env("SEARCH_MAX_RESULTS", "6"))
# 搜索后端可插拔：
#   ddgs=DuckDuckGo(境外可用)  exa=Exa AI  http=通用付费搜索API  off=关闭
#   tavily=Tavily(AI 检索, 返回清洗正文+相关性分数, 需 SEARCH_API_KEY)
#   bocha=博查(国内, 对中文实体友好, 需 SEARCH_API_KEY)
SEARCH_PROVIDER = _env("SEARCH_PROVIDER", "ddgs").lower()
SEARCH_API_URL = _env("SEARCH_API_URL", "")
SEARCH_API_KEY = _env("SEARCH_API_KEY", "")
# 排序后保留并喂给 LLM 的最大结果数（控制 token 成本与噪声）
SEARCH_TOP_K = int(_env("SEARCH_TOP_K", "18"))

# ---------- 注入量上限与去噪（控制喂给 LLM 的上下文体量：省 token、降噪声、防超时）----------
# 搜索上下文：单条摘要字符上限 + 汇总总字符上限（超出按句子/换行边界截断）。
# bocha/tavily 单条正文可达 1000 字，18 条汇总易撑爆便宜档上下文并拖慢/超时，这里再收一道。
SEARCH_SNIPPET_MAX_CHARS = int(_env("SEARCH_SNIPPET_MAX_CHARS", "400"))
SEARCH_CONTEXT_MAX_CHARS = int(_env("SEARCH_CONTEXT_MAX_CHARS", "9000"))
# 知识库注入：最多注入条数 + 单条正文字符上限 + 汇总总字符上限（并对重复切片去重）。
KNOWLEDGE_MAX_ITEMS = int(_env("KNOWLEDGE_MAX_ITEMS", "5"))
KNOWLEDGE_ITEM_MAX_CHARS = int(_env("KNOWLEDGE_ITEM_MAX_CHARS", "700"))
KNOWLEDGE_CONTEXT_MAX_CHARS = int(_env("KNOWLEDGE_CONTEXT_MAX_CHARS", "3000"))
# 客户记忆注入：历史事实/销售跟进的最大条数（原为硬编码 10/6，现可调）。
MEMORY_MAX_FACTS = int(_env("MEMORY_MAX_FACTS", "8"))
MEMORY_MAX_NOTES = int(_env("MEMORY_MAX_NOTES", "5"))

# ---------- 用量控制 ----------
# 每个用户每天可免费提交的分析次数（按北京时间自然日计算），超出后拒绝提交
DAILY_FREE_LIMIT = int(_env("DAILY_FREE_LIMIT", "5"))

# ---------- 管理后台 ----------
# 允许进入管理后台的微信 openid 白名单，逗号分隔（只读 .env，防止越权自助提权）
ADMIN_OPENIDS = {x.strip() for x in _env("ADMIN_OPENIDS", "").split(",") if x.strip()}
# 独立网页版知识库上传页的访问口令（网页无法走微信登录，用共享口令保护）。留空则该页禁用。
ADMIN_UPLOAD_TOKEN = _env("ADMIN_UPLOAD_TOKEN", "")
# 网页上传单文件大小上限（MB）
KNOWLEDGE_MAX_UPLOAD_MB = int(_env("KNOWLEDGE_MAX_UPLOAD_MB", "20"))

# ---------- 结果缓存 ----------
# 同一用户重复分析同一客户时，多少天内的成功报告可直接复用（不重跑大模型、不耗额度）
CACHE_TTL_DAYS = int(_env("CACHE_TTL_DAYS", "7"))
