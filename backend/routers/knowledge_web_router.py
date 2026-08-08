"""独立网页版知识库上传页：拖入 Word/PDF -> 解析 -> 小模型提炼 -> 审核 -> 入库。

鉴权：网页无法走微信登录，改用共享口令 config.ADMIN_UPLOAD_TOKEN（前端在请求头
X-Upload-Token 里带上）。口令留空则整个页面与接口禁用。

页面通过 HTMLResponse 直接返回（无需静态目录）。入库复用 database.create_knowledge_document。
"""
import logging

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

import config
import database
from agent import knowledge_ingest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["knowledge-web"])

# 网页上传文档的 created_by：网页无微信用户身份，用 0 作哨兵值（created_by 无 FK 约束）
_WEB_UPLOAD_USER_ID = 0


def require_upload_token(x_upload_token: str = Header(default="")) -> None:
    """校验共享上传口令。"""
    if not config.ADMIN_UPLOAD_TOKEN:
        raise HTTPException(status_code=503, detail="服务端未配置 ADMIN_UPLOAD_TOKEN，网页上传已禁用")
    if (x_upload_token or "").strip() != config.ADMIN_UPLOAD_TOKEN:
        raise HTTPException(status_code=401, detail="上传口令错误")


class KnowledgeSaveRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=20, max_length=100000)
    category: str = Field(default="general", max_length=50)
    source_url: str = Field(default="", max_length=1000)


@router.get("/kb", response_class=HTMLResponse)
def kb_page() -> str:
    """返回知识库上传页面（自包含单文件 HTML）。"""
    return _PAGE_HTML


@router.post("/api/kb/extract")
async def kb_extract(
    file: UploadFile = File(...),
    _: None = Depends(require_upload_token),
) -> dict:
    """解析上传文件并调用小模型提炼，返回预览（不入库）。"""
    data = await file.read()
    max_bytes = config.KNOWLEDGE_MAX_UPLOAD_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"文件超过 {config.KNOWLEDGE_MAX_UPLOAD_MB}MB 上限")
    if not data:
        raise HTTPException(status_code=400, detail="文件为空")
    try:
        raw_text = knowledge_ingest.extract_text(file.filename, data)
    except knowledge_ingest.IngestError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    try:
        distilled = knowledge_ingest.distill(file.filename, raw_text)
    except knowledge_ingest.IngestError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 — 提炼失败（模型/网络）统一转 502
        logger.exception("知识提炼失败")
        raise HTTPException(status_code=502, detail=f"提炼失败：{exc}")
    stored_content = knowledge_ingest.compose_stored_content(distilled)
    return {
        "filename": file.filename,
        "title": distilled["title"],
        "category": distilled["category"],
        "summary": distilled["summary"],
        "tags": distilled["tags"],
        "content": stored_content,
        "raw_chars": distilled["raw_chars"],
        "truncated": distilled["truncated"],
    }


@router.post("/api/kb/save")
def kb_save(
    body: KnowledgeSaveRequest,
    _: None = Depends(require_upload_token),
) -> dict:
    """把（可能经人工编辑的）提炼结果写入知识库。"""
    doc = database.create_knowledge_document(
        _WEB_UPLOAD_USER_ID, body.title, body.content, body.category, body.source_url
    )
    logger.info("网页上传入库知识文档 #%s：%s", doc["id"], doc["title"])
    return {"id": doc["id"], "title": doc["title"]}


@router.get("/api/kb/list")
def kb_list(_: None = Depends(require_upload_token)) -> dict:
    return {"items": database.list_knowledge_admin()}


_PAGE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>ClassIn KA 知识库上传</title>
<style>
  * { box-sizing: border-box; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
         background:#f5f7fa; color:#1f2733; }
  .wrap { max-width:820px; margin:0 auto; padding:24px 16px 80px; }
  h1 { font-size:22px; margin:8px 0 4px; }
  .sub { color:#8a919f; font-size:13px; margin-bottom:20px; }
  .card { background:#fff; border-radius:12px; padding:20px; box-shadow:0 1px 3px rgba(0,0,0,.06); margin-bottom:16px; }
  label { display:block; font-size:13px; color:#5b6472; margin:12px 0 6px; }
  input[type=text], input[type=password], textarea, select {
    width:100%; border:1.5px solid #e5e8ee; border-radius:8px; padding:10px 12px; font-size:14px; background:#fff; }
  textarea { min-height:220px; line-height:1.6; resize:vertical; font-family:inherit; }
  .drop { border:2px dashed #c6cdd8; border-radius:12px; padding:36px 16px; text-align:center; color:#8a919f;
          cursor:pointer; transition:.15s; }
  .drop.hover { border-color:#2b6de5; background:#f0f6ff; color:#2b6de5; }
  .drop b { color:#2b6de5; }
  .btn { display:inline-block; border:none; border-radius:8px; padding:11px 22px; font-size:14px; cursor:pointer;
         background:#2b6de5; color:#fff; }
  .btn:disabled { opacity:.5; cursor:not-allowed; }
  .btn.ghost { background:#eef1f6; color:#3a4250; }
  .row { display:flex; gap:12px; flex-wrap:wrap; align-items:center; }
  .tag { display:inline-block; background:#eef4ff; color:#2b6de5; border-radius:6px; padding:2px 10px; font-size:12px; margin:0 6px 6px 0; }
  .msg { font-size:13px; margin-top:12px; min-height:18px; }
  .msg.err { color:#f5222d; } .msg.ok { color:#20a15b; }
  .hint { font-size:12px; color:#8a919f; margin-top:6px; }
  .hidden { display:none; }
  .k-item { border-top:1px solid #f0f2f5; padding:10px 0; font-size:13px; }
  .k-item .c { color:#8a919f; }
  .spin { display:inline-block; width:14px; height:14px; border:2px solid #cbd5e1; border-top-color:#2b6de5;
          border-radius:50%; animation:sp .7s linear infinite; vertical-align:-2px; margin-right:6px; }
  @keyframes sp { to { transform:rotate(360deg); } }
</style>
</head>
<body>
<div class="wrap">
  <h1>ClassIn KA 知识库上传</h1>
  <div class="sub">拖入 Word / PDF / 文本，自动解析并用模型提炼成结构化知识条目，审核后入库。仅支持电子版文字文档（不含扫描件 OCR）。</div>

  <div class="card">
    <label>访问口令</label>
    <input type="password" id="token" placeholder="请输入上传口令（ADMIN_UPLOAD_TOKEN）" />
    <div class="hint">口令仅保存在当前页面内存中，不会上传或长期存储。</div>
  </div>

  <div class="card">
    <div class="drop" id="drop">
      <div>把文件拖到这里，或 <b>点击选择文件</b></div>
      <div class="hint" id="fileHint">支持 .docx / .pdf / .txt / .md</div>
    </div>
    <input type="file" id="file" class="hidden" accept=".docx,.pdf,.txt,.md,.markdown" />
    <div class="row" style="margin-top:16px">
      <button class="btn" id="extractBtn" disabled>解析并提炼</button>
    </div>
    <div class="msg" id="extractMsg"></div>
  </div>

  <div class="card hidden" id="preview">
    <label>标题</label>
    <input type="text" id="pTitle" />
    <label>分类</label>
    <select id="pCategory">
      <option value="product">product（产品方案）</option>
      <option value="case">case（行业案例）</option>
      <option value="competitor">competitor（竞品对比）</option>
      <option value="faq">faq（常见异议问答）</option>
      <option value="general">general（其他）</option>
    </select>
    <label>标签</label>
    <div id="pTags"></div>
    <label>入库正文（可编辑后再保存）</label>
    <textarea id="pContent"></textarea>
    <label>来源（可选）</label>
    <input type="text" id="pSource" placeholder="原始文件名 / 链接" />
    <div class="row" style="margin-top:16px">
      <button class="btn" id="saveBtn">保存入库</button>
      <button class="btn ghost" id="cancelBtn">放弃</button>
    </div>
    <div class="msg" id="saveMsg"></div>
  </div>

  <div class="card">
    <div class="row" style="justify-content:space-between">
      <b style="font-size:15px">已有知识文档</b>
      <button class="btn ghost" id="reloadBtn">刷新</button>
    </div>
    <div id="list"><div class="hint">输入口令后点刷新查看。</div></div>
  </div>
</div>

<script>
const $ = (id) => document.getElementById(id);
let chosenFile = null;
let extracted = null;

function token() { return $("token").value.trim(); }
function headers() { return { "X-Upload-Token": token() }; }

const drop = $("drop"), fileInput = $("file");
drop.addEventListener("click", () => fileInput.click());
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("hover"); });
drop.addEventListener("dragleave", () => drop.classList.remove("hover"));
drop.addEventListener("drop", (e) => {
  e.preventDefault(); drop.classList.remove("hover");
  if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => { if (fileInput.files.length) setFile(fileInput.files[0]); });

function setFile(f) {
  chosenFile = f;
  $("fileHint").textContent = "已选择：" + f.name;
  $("extractBtn").disabled = false;
}

$("extractBtn").addEventListener("click", async () => {
  if (!token()) { showMsg("extractMsg", "请先输入访问口令", true); return; }
  if (!chosenFile) return;
  const fd = new FormData(); fd.append("file", chosenFile);
  $("extractBtn").disabled = true;
  showMsg("extractMsg", '<span class="spin"></span>正在解析并提炼，请稍候…', false);
  try {
    const resp = await fetch("/api/kb/extract", { method:"POST", headers: headers(), body: fd });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "解析失败");
    extracted = data;
    fillPreview(data);
    showMsg("extractMsg", "提炼完成，请在下方审核后保存。" + (data.truncated ? "（原文较长已截断前 2 万字）" : ""), false);
  } catch (err) {
    showMsg("extractMsg", err.message, true);
  } finally {
    $("extractBtn").disabled = false;
  }
});

function fillPreview(d) {
  $("pTitle").value = d.title || "";
  $("pCategory").value = d.category || "general";
  $("pContent").value = d.content || "";
  $("pSource").value = d.filename || "";
  $("pTags").innerHTML = (d.tags || []).map(t => '<span class="tag">' + escapeHtml(t) + '</span>').join("") || '<span class="hint">无</span>';
  $("preview").classList.remove("hidden");
  $("preview").scrollIntoView({ behavior:"smooth" });
}

$("saveBtn").addEventListener("click", async () => {
  const body = {
    title: $("pTitle").value.trim(),
    category: $("pCategory").value,
    content: $("pContent").value.trim(),
    source_url: $("pSource").value.trim(),
  };
  if (body.title.length < 1 || body.content.length < 20) { showMsg("saveMsg", "标题必填，正文至少 20 字", true); return; }
  $("saveBtn").disabled = true;
  showMsg("saveMsg", '<span class="spin"></span>保存中…', false);
  try {
    const resp = await fetch("/api/kb/save", {
      method:"POST", headers: { ...headers(), "Content-Type":"application/json" }, body: JSON.stringify(body)
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "保存失败");
    showMsg("saveMsg", "已入库 #" + data.id + "：" + data.title, false, true);
    $("preview").classList.add("hidden");
    chosenFile = null; extracted = null;
    $("fileHint").textContent = "支持 .docx / .pdf / .txt / .md";
    $("extractBtn").disabled = true;
    loadList();
  } catch (err) {
    showMsg("saveMsg", err.message, true);
  } finally {
    $("saveBtn").disabled = false;
  }
});

$("cancelBtn").addEventListener("click", () => { $("preview").classList.add("hidden"); });
$("reloadBtn").addEventListener("click", loadList);

async function loadList() {
  if (!token()) { $("list").innerHTML = '<div class="hint">请先输入口令</div>'; return; }
  try {
    const resp = await fetch("/api/kb/list", { headers: headers() });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "加载失败");
    const items = data.items || [];
    if (!items.length) { $("list").innerHTML = '<div class="hint">暂无文档</div>'; return; }
    $("list").innerHTML = items.map(it =>
      '<div class="k-item"><b>' + escapeHtml(it.title) + '</b> <span class="c">（' +
      escapeHtml(it.category || "general") + " · " + escapeHtml(it.status || "active") + '）</span></div>'
    ).join("");
  } catch (err) {
    $("list").innerHTML = '<div class="hint" style="color:#f5222d">' + escapeHtml(err.message) + '</div>';
  }
}

function showMsg(id, html, isErr, isOk) {
  const el = $(id); el.className = "msg" + (isErr ? " err" : (isOk ? " ok" : "")); el.innerHTML = html;
}
function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => (
    { "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
}
</script>
</body>
</html>"""
