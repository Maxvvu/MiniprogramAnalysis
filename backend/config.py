"""全局配置：优先读取环境变量，其次读取 backend/.env 文件。"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


# ---------- 服务 ----------
HOST = _env("HOST", "0.0.0.0")
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
JWT_SECRET = _env("JWT_SECRET", "change-me-in-production")
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

# ---------- 联网搜索 ----------
SEARCH_ENABLED = _env("SEARCH_ENABLED", "true").lower() != "false"
SEARCH_MAX_RESULTS = int(_env("SEARCH_MAX_RESULTS", "6"))
# 搜索后端可插拔：ddgs=DuckDuckGo(境外可用) http=通用付费搜索API off=关闭
SEARCH_PROVIDER = _env("SEARCH_PROVIDER", "ddgs").lower()
SEARCH_API_URL = _env("SEARCH_API_URL", "")
SEARCH_API_KEY = _env("SEARCH_API_KEY", "")

# ---------- 用量控制 ----------
# 每个用户每天可免费提交的分析次数（按北京时间自然日计算），超出后拒绝提交
DAILY_FREE_LIMIT = int(_env("DAILY_FREE_LIMIT", "5"))

# ---------- 管理后台 ----------
# 允许进入管理后台的微信 openid 白名单，逗号分隔（只读 .env，防止越权自助提权）
ADMIN_OPENIDS = {x.strip() for x in _env("ADMIN_OPENIDS", "").split(",") if x.strip()}

# ---------- 结果缓存 ----------
# 同一用户重复分析同一客户时，多少天内的成功报告可直接复用（不重跑大模型、不耗额度）
CACHE_TTL_DAYS = int(_env("CACHE_TTL_DAYS", "7"))
