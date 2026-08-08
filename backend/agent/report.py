"""报告生成：把分析结果渲染为 Markdown 与 Word 文档。"""
import re
import time
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

import config

# 报告章节顺序：(JSON key, 章节标题, 类型)
SECTIONS = [
    ("summary", "一、客户总览与销售结论", "text"),
    ("overview", "二、客户概况", "text"),
    ("business_model", "三、业务模式与主打产品", "text"),
    ("conflicts", "四、数据冲突提示", "conflicts"),
    ("growth", "五、增量情况分析", "growth"),
    ("revenue_payment", "六、营收与付费能力", "text"),
    ("digitalization", "七、数字化与在线教学现状", "text"),
    ("competitors", "八、竞品使用情况分析", "competitors"),
    ("classin_fit", "九、ClassIn 模块匹配度", "classin_fit"),
    ("ka_rating", "十、KA 客户分级", "rating"),
    ("sales_direction", "十一、销售方向与打法建议", "sales"),
    ("decision_chain", "十二、决策链与关键人", "decision_chain"),
    ("competitive_intel", "十三、竞争情报", "competitive_intel"),
    ("reputation_compliance", "十四、舆情与合规风险", "reputation_compliance"),
    ("risks", "十五、风险与注意事项", "text"),
    ("confidence", "十六、分析置信度", "confidence"),
    ("info_note", "十七、信息来源说明", "text"),
]

# 中文文件名安全字符范围（等价于 \u4e00-\u9fff）
_CN = "一-鿿"


def _clean(text: str) -> str:
    """去掉 markdown 加粗等符号，输出纯文本。"""
    return re.sub(r"\*\*(.+?)\*\*", r"\1", str(text)).strip()


def _fact_text(fact: object) -> str:
    return fact.get("fact", "") if isinstance(fact, dict) else str(fact)


def _fmt_marked(item: object, key: str) -> str:
    """把证据链对象 {key, is_inference, basis, confidence} 渲染成可读的一行。"""
    if not isinstance(item, dict):
        return _clean(item)
    text = _clean(item.get(key, ""))
    tags = []
    if item.get("is_inference"):
        tags.append("推断")
    conf = item.get("confidence")
    if conf:
        tags.append(f"置信度{conf}")
    basis = _clean(item.get("basis", ""))
    suffix = ""
    if tags or basis:
        parts = "，".join(tags)
        if basis:
            parts = (parts + "；" if parts else "") + f"依据：{basis}"
        suffix = f"（{parts}）"
    return f"{text}{suffix}"


def _safe_filename(name: str) -> str:
    return re.sub(r"[^\w" + _CN + r"-]", "_", name)


def render_markdown(name: str, customer_type: str, analysis: dict, profile: dict) -> str:
    lines = [
        f"# KA 客户分析报告：{name}",
        "",
        f"- 客户类型：{'教培机构' if customer_type == 'institution' else '个体教师'}",
        f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M')}",
        f"- KA 分级：**{analysis.get('ka_rating', {}).get('level', '未评级')}**",
        "",
        "---",
        "",
    ]
    for key, title, kind in SECTIONS:
        value = analysis.get(key)
        if not value:
            continue
        lines.append(f"## {title}")
        lines.append("")

        if kind == "rating":
            lines.append(f"**分级：{value.get('level', '')}**")
            lines.append(f"**年付费潜力：{value.get('annual_potential', '未知')}**")
            lines.append("")
            lines.append(_clean(value.get("reason", "")))

        elif kind == "growth":
            lines.append(f"**当前规模**：{value.get('current_scale', '未知')}")
            lines.append(f"**增长率**：{value.get('growth_rate', '未知')}")
            lines.append("")
            lines.append("**近期扩张动作：**")
            for action in value.get("expansion_actions", []):
                lines.append(f"- {_fmt_marked(action, 'action')}")
            lines.append("")
            lines.append("**未来增量驱动力：**")
            for driver in value.get("increment_drivers", []):
                lines.append(f"- {_fmt_marked(driver, 'driver')}")
            lines.append("")
            tw = value.get("timing_window", {})
            lines.append(f"**最佳切入时间**：{tw.get('best_timing', '待确认')}")
            lines.append(f"**需求紧迫度**：{tw.get('urgency', 'medium')}")
            lines.append(f"**理由**：{_clean(tw.get('reason', ''))}")
            lines.append("")
            lines.append(f"**增量潜力**：{value.get('potential_value', '待评估')}")

        elif kind == "competitors":
            lines.append("**当前工具推断：**")
            lines.append("")
            for tool in value.get("current_tools", []):
                lines.append(f"### {tool.get('product', '未知工具')}")
                lines.append(f"- **使用场景**：{tool.get('usage_scenario', '未知')}")
                lines.append(f"- **痛点**：{', '.join(tool.get('pain_points', []))}")
                lines.append(f"- **替换机会**：{tool.get('replacement_opportunity', 'medium')}")
                mark = "推断" if tool.get("is_inference") else "事实"
                lines.append(f"- **依据（{mark}）**：{_clean(tool.get('basis', '未标注'))}")
                lines.append("")
            lines.append(f"**替换成本**：{_clean(value.get('switch_barriers', '待评估'))}")
            lines.append("")
            lines.append(f"**共存策略**：{_clean(value.get('coexist_strategy', '待确认'))}")

        elif kind == "sales":
            lines.append("### 推荐切入点（按优先级排序）")
            for item in value.get("entry_points", []):
                if isinstance(item, dict):
                    lines.append(f"**优先级 {item.get('priority', '?')}** - {_clean(item.get('point', ''))}")
                    lines.append(f"  - 有效性：{_clean(item.get('why_effective', ''))}")
                    lines.append(f"  - 成功率：{item.get('success_rate', 'medium')}")
                    lines.append(f"  - 预估价值：{item.get('estimated_value', '待评估')}")
                else:
                    lines.append(f"- {_clean(item)}")
            lines.append("")
            lines.append("### 首次接触建议")
            for item in value.get("first_actions", []):
                lines.append(f"- {_clean(item)}")
            lines.append("")
            lines.append("### 预期异议与应对")
            for item in value.get("objections", []):
                lines.append(f"- **异议**：{_clean(item.get('objection', ''))}")
                lines.append(f"  **应对**：{_clean(item.get('response', ''))}")

        elif kind == "competitive_intel":
            lines.append(f"**同行对比**：{_clean(value.get('peer_comparison', '待分析'))}")
            lines.append(f"**市场地位**：{_clean(value.get('market_position', '待确认'))}")
            lines.append(f"**竞对威胁**：{value.get('threat_level', 'medium')}")

        elif kind == "confidence":
            lines.append(f"**整体置信度**：{value.get('overall', 'medium')}")
            lines.append(f"**搜索质量**：{_clean(value.get('search_quality', ''))}")
            lines.append(f"**数据完整度**：{_clean(value.get('data_completeness', ''))}")
            lines.append(f"**推断占比**：{_clean(value.get('inference_ratio', ''))}")
            lines.append("")
            lines.append(f"**建议**：{_clean(value.get('recommendation', ''))}")

        elif kind == "conflicts":
            for item in value:
                if not isinstance(item, dict):
                    continue
                lines.append(f"- **{_clean(item.get('item', ''))}**")
                for ver in item.get("versions", []):
                    lines.append(f"  - 说法：{_clean(ver)}")
                lines.append(f"  - 倾向采信：{_clean(item.get('preferred', ''))}")
                lines.append(f"  - 理由：{_clean(item.get('reason', ''))}")

        elif kind == "classin_fit":
            lines.append(f"**综合匹配度**：{value.get('overall_score', '未知')}")
            lines.append(f"**总体判断**：{_clean(value.get('summary', ''))}")
            lines.append("")
            for m in value.get("modules", []):
                lines.append(f"- **{_clean(m.get('module', ''))}**（{m.get('fit_score', '?')}分）：{_clean(m.get('reason', ''))}")

        elif kind == "decision_chain":
            lines.append("**关键角色：**")
            for role in value.get("key_roles", []):
                mark = "（推断）" if role.get("is_inference") else ""
                lines.append(f"- **{_clean(role.get('role', ''))}**{mark}：关注 {_clean(role.get('concern', ''))}；依据：{_clean(role.get('basis', ''))}")
            lines.append("")
            lines.append(f"**建议触达路径**：{_clean(value.get('recommended_path', ''))}")
            lines.append(f"**预算归属**：{_clean(value.get('budget_owner', '未知'))}")

        elif kind == "reputation_compliance":
            lines.append(f"**舆情概览**：{_clean(value.get('public_sentiment', ''))}")
            complaints = value.get("complaints", [])
            if complaints:
                lines.append("**投诉/负面：**")
                for c in complaints:
                    lines.append(f"- {_clean(c)}")
            lines.append(f"**资质合规风险**：{_clean(value.get('qualification_risk', '未知'))}")
            lines.append(f"**风险等级**：{value.get('risk_level', 'medium')}")

        else:
            lines.append(_clean(value))

        lines.append("")

    reg = profile.get("business_registration")
    if isinstance(reg, dict) and any(str(v).strip() not in ("", "未知") for v in reg.values()):
        lines.append("## 附录一：工商档案")
        lines.append("")
        reg_fields = [
            ("legal_name", "工商全称"), ("established", "成立时间"),
            ("registered_capital", "注册资本"), ("legal_representative", "法定代表人"),
            ("status", "经营状态"), ("branch_count", "分支机构/校区数"),
            ("credit_code", "统一社会信用代码"), ("source_tier", "来源可信度"),
        ]
        for key, label in reg_fields:
            val = reg.get(key)
            if val and str(val).strip() != "未知":
                lines.append(f"- **{label}**：{_clean(val)}")
        lines.append("")

    signals = profile.get("hiring_signals")
    if isinstance(signals, list) and signals:
        lines.append("## 附录二：招聘与扩张信号")
        lines.append("")
        for s in signals:
            if not isinstance(s, dict):
                continue
            conf = s.get("confidence", "")
            lines.append(f"- {_clean(s.get('signal', ''))} → {_clean(s.get('implication', ''))}（置信度{conf}）")
        lines.append("")

    if profile.get("facts"):
        lines.append("## 附录三：事实档案")
        lines.append("")
        for fact in profile["facts"]:
            text = _clean(_fact_text(fact))
            if isinstance(fact, dict):
                meta = []
                if fact.get("source_tier"):
                    meta.append(str(fact["source_tier"]))
                if fact.get("published_at") and fact["published_at"] != "未知":
                    meta.append(str(fact["published_at"]))
                if fact.get("confidence"):
                    meta.append(f"置信度{fact['confidence']}")
                if meta:
                    text += f"（{'｜'.join(meta)}）"
            lines.append(f"- {text}")
    return "\n".join(lines)


def _set_cn_font(doc: Document) -> None:
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)
    style._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")


def generate_docx(name: str, customer_type: str, analysis: dict, profile: dict) -> Path:
    doc = Document()
    _set_cn_font(doc)

    title = doc.add_heading(f"KA 客户分析报告：{name}", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    level = analysis.get("ka_rating", {}).get("level", "未评级")
    run = meta.add_run(
        f"客户类型：{'教培机构' if customer_type == 'institution' else '个体教师'}    "
        f"KA 分级：{level}    生成时间：{time.strftime('%Y-%m-%d %H:%M')}"
    )
    run.font.size = Pt(10)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    for key, heading, kind in SECTIONS:
        value = analysis.get(key)
        if not value:
            continue
        doc.add_heading(heading, level=1)

        if kind == "rating":
            p = doc.add_paragraph()
            r = p.add_run(f"分级：{value.get('level', '')}  年付费潜力：{value.get('annual_potential', '未知')}")
            r.bold = True
            r.font.size = Pt(14)
            doc.add_paragraph(_clean(value.get("reason", "")))

        elif kind == "growth":
            doc.add_paragraph(f"当前规模：{value.get('current_scale', '未知')}")
            doc.add_paragraph(f"增长率：{value.get('growth_rate', '未知')}")
            doc.add_heading("近期扩张动作", level=2)
            for action in value.get("expansion_actions", []):
                doc.add_paragraph(_fmt_marked(action, "action"), style="List Bullet")
            doc.add_heading("未来增量驱动力", level=2)
            for driver in value.get("increment_drivers", []):
                doc.add_paragraph(_fmt_marked(driver, "driver"), style="List Bullet")
            tw = value.get("timing_window", {})
            doc.add_paragraph(f"最佳切入时间：{tw.get('best_timing', '待确认')}")
            doc.add_paragraph(f"需求紧迫度：{tw.get('urgency', 'medium')}")
            doc.add_paragraph(f"理由：{_clean(tw.get('reason', ''))}")
            doc.add_paragraph(f"增量潜力：{value.get('potential_value', '待评估')}")

        elif kind == "competitors":
            doc.add_heading("当前工具推断", level=2)
            for tool in value.get("current_tools", []):
                p = doc.add_paragraph()
                r = p.add_run(tool.get('product', '未知工具'))
                r.bold = True
                doc.add_paragraph(f"使用场景：{tool.get('usage_scenario', '未知')}")
                doc.add_paragraph(f"痛点：{', '.join(tool.get('pain_points', []))}")
                doc.add_paragraph(f"替换机会：{tool.get('replacement_opportunity', 'medium')}")
                mark = "推断" if tool.get("is_inference") else "事实"
                doc.add_paragraph(f"依据（{mark}）：{_clean(tool.get('basis', '未标注'))}")
            doc.add_paragraph(f"替换成本：{_clean(value.get('switch_barriers', '待评估'))}")
            doc.add_paragraph(f"共存策略：{_clean(value.get('coexist_strategy', '待确认'))}")

        elif kind == "sales":
            doc.add_heading("推荐切入点（按优先级排序）", level=2)
            for item in value.get("entry_points", []):
                if isinstance(item, dict):
                    p = doc.add_paragraph(style="List Bullet")
                    r = p.add_run(f"优先级 {item.get('priority', '?')} - {_clean(item.get('point', ''))}")
                    r.bold = True
                    doc.add_paragraph(f"有效性：{_clean(item.get('why_effective', ''))}")
                    doc.add_paragraph(f"成功率：{item.get('success_rate', 'medium')}")
                    doc.add_paragraph(f"预估价值：{item.get('estimated_value', '待评估')}")
                else:
                    doc.add_paragraph(_clean(item), style="List Bullet")
            doc.add_heading("首次接触建议", level=2)
            for item in value.get("first_actions", []):
                doc.add_paragraph(_clean(item), style="List Bullet")
            doc.add_heading("预期异议与应对", level=2)
            for item in value.get("objections", []):
                p = doc.add_paragraph(style="List Bullet")
                r = p.add_run(f"异议：{_clean(item.get('objection', ''))}")
                r.bold = True
                doc.add_paragraph(f"应对：{_clean(item.get('response', ''))}")

        elif kind == "competitive_intel":
            doc.add_paragraph(f"同行对比：{_clean(value.get('peer_comparison', '待分析'))}")
            doc.add_paragraph(f"市场地位：{_clean(value.get('market_position', '待确认'))}")
            doc.add_paragraph(f"竞对威胁：{value.get('threat_level', 'medium')}")

        elif kind == "confidence":
            doc.add_paragraph(f"整体置信度：{value.get('overall', 'medium')}")
            doc.add_paragraph(f"搜索质量：{_clean(value.get('search_quality', ''))}")
            doc.add_paragraph(f"数据完整度：{_clean(value.get('data_completeness', ''))}")
            doc.add_paragraph(f"推断占比：{_clean(value.get('inference_ratio', ''))}")
            doc.add_paragraph(f"建议：{_clean(value.get('recommendation', ''))}")

        elif kind == "conflicts":
            for item in value:
                if not isinstance(item, dict):
                    continue
                p = doc.add_paragraph(style="List Bullet")
                r = p.add_run(_clean(item.get("item", "")))
                r.bold = True
                for ver in item.get("versions", []):
                    doc.add_paragraph(f"说法：{_clean(ver)}")
                doc.add_paragraph(f"倾向采信：{_clean(item.get('preferred', ''))}")
                doc.add_paragraph(f"理由：{_clean(item.get('reason', ''))}")

        elif kind == "classin_fit":
            doc.add_paragraph(f"综合匹配度：{value.get('overall_score', '未知')}")
            doc.add_paragraph(f"总体判断：{_clean(value.get('summary', ''))}")
            for m in value.get("modules", []):
                p = doc.add_paragraph(style="List Bullet")
                r = p.add_run(f"{_clean(m.get('module', ''))}（{m.get('fit_score', '?')}分）")
                r.bold = True
                doc.add_paragraph(_clean(m.get("reason", "")))

        elif kind == "decision_chain":
            doc.add_heading("关键角色", level=2)
            for role in value.get("key_roles", []):
                p = doc.add_paragraph(style="List Bullet")
                mark = "（推断）" if role.get("is_inference") else ""
                r = p.add_run(f"{_clean(role.get('role', ''))}{mark}")
                r.bold = True
                doc.add_paragraph(f"关注：{_clean(role.get('concern', ''))}")
                doc.add_paragraph(f"依据：{_clean(role.get('basis', ''))}")
            doc.add_paragraph(f"建议触达路径：{_clean(value.get('recommended_path', ''))}")
            doc.add_paragraph(f"预算归属：{_clean(value.get('budget_owner', '未知'))}")

        elif kind == "reputation_compliance":
            doc.add_paragraph(f"舆情概览：{_clean(value.get('public_sentiment', ''))}")
            complaints = value.get("complaints", [])
            if complaints:
                doc.add_heading("投诉/负面", level=2)
                for c in complaints:
                    doc.add_paragraph(_clean(c), style="List Bullet")
            doc.add_paragraph(f"资质合规风险：{_clean(value.get('qualification_risk', '未知'))}")
            doc.add_paragraph(f"风险等级：{value.get('risk_level', 'medium')}")

        else:
            doc.add_paragraph(_clean(value))

    reg = profile.get("business_registration")
    if isinstance(reg, dict) and any(str(v).strip() not in ("", "未知") for v in reg.values()):
        doc.add_heading("附录一：工商档案", level=1)
        reg_fields = [
            ("legal_name", "工商全称"), ("established", "成立时间"),
            ("registered_capital", "注册资本"), ("legal_representative", "法定代表人"),
            ("status", "经营状态"), ("branch_count", "分支机构/校区数"),
            ("credit_code", "统一社会信用代码"), ("source_tier", "来源可信度"),
        ]
        for fkey, label in reg_fields:
            val = reg.get(fkey)
            if val and str(val).strip() != "未知":
                doc.add_paragraph(f"{label}：{_clean(val)}", style="List Bullet")

    signals = profile.get("hiring_signals")
    if isinstance(signals, list) and signals:
        doc.add_heading("附录二：招聘与扩张信号", level=1)
        for s in signals:
            if not isinstance(s, dict):
                continue
            conf = s.get("confidence", "")
            doc.add_paragraph(
                f"{_clean(s.get('signal', ''))} → {_clean(s.get('implication', ''))}（置信度{conf}）",
                style="List Bullet",
            )

    if profile.get("facts"):
        doc.add_heading("附录三：事实档案", level=1)
        for fact in profile["facts"]:
            text = _clean(_fact_text(fact))
            if isinstance(fact, dict):
                meta_parts = []
                if fact.get("source_tier"):
                    meta_parts.append(str(fact["source_tier"]))
                if fact.get("published_at") and fact["published_at"] != "未知":
                    meta_parts.append(str(fact["published_at"]))
                if fact.get("confidence"):
                    meta_parts.append(f"置信度{fact['confidence']}")
                if meta_parts:
                    text += f"（{'｜'.join(meta_parts)}）"
            doc.add_paragraph(text, style="List Bullet")

    path = config.REPORT_DIR / f"{_safe_filename(name)}_{time.strftime('%Y%m%d%H%M%S')}.docx"
    doc.save(path)
    return path


# ---------- 面向客户的解决方案 ----------

def render_solution_markdown(name: str, solution: dict) -> str:
    lines = [
        f"# {solution.get('title', f'{name} 解决方案')}",
        "",
        f"呈送：{name}　　编制：ClassIn 企业培训事业部　　{time.strftime('%Y-%m-%d')}",
        "",
        "---",
        "",
        "## 一、我们对贵方业务的理解",
        "",
        _clean(solution.get("understanding", "")),
        "",
        "## 二、当前面临的核心挑战",
        "",
    ]
    for c in solution.get("challenges", []):
        lines.append(f"- {_clean(c)}")
    lines += ["", "## 三、方案总体思路", "", _clean(solution.get("solution_overview", "")), "",
              "## 四、推荐能力模块", ""]
    for m in solution.get("modules", []):
        lines.append(f"### {_clean(m.get('name', ''))}")
        lines.append("")
        lines.append(f"作用：{_clean(m.get('purpose', ''))}")
        lines.append("")
        lines.append(f"价值：{_clean(m.get('value', ''))}")
        lines.append("")
    lines += ["## 五、场景化设计", ""]
    for s in solution.get("scenarios", []):
        lines.append(f"### {_clean(s.get('name', ''))}")
        lines.append("")
        lines.append(_clean(s.get("description", "")))
        lines.append("")
        lines.append(f"预期效果：{_clean(s.get('expected_effect', ''))}")
        lines.append("")
    lines += ["## 六、实施路径", ""]
    for r in solution.get("roadmap", []):
        lines.append(f"**{_clean(r.get('phase', ''))}**：{_clean(r.get('actions', ''))}")
        lines.append("")
    lines += [
        "## 七、投入构成",
        "",
        _clean(solution.get("investment", "")),
        "",
        "## 八、预期回报",
        "",
        _clean(solution.get("roi", "")),
        "",
        "## 九、为什么选择 ClassIn",
        "",
        _clean(solution.get("why_classin", "")),
        "",
    ]
    return "\n".join(lines)


def generate_solution_docx(name: str, solution: dict) -> Path:
    doc = Document()
    _set_cn_font(doc)

    title = doc.add_heading(solution.get("title", f"{name} 解决方案"), level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = meta.add_run(
        f"呈送：{name}　　编制：ClassIn 企业培训事业部　　{time.strftime('%Y-%m-%d')}"
    )
    run.font.size = Pt(10)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    doc.add_heading("一、我们对贵方业务的理解", level=1)
    doc.add_paragraph(_clean(solution.get("understanding", "")))

    doc.add_heading("二、当前面临的核心挑战", level=1)
    for c in solution.get("challenges", []):
        doc.add_paragraph(_clean(c), style="List Bullet")

    doc.add_heading("三、方案总体思路", level=1)
    doc.add_paragraph(_clean(solution.get("solution_overview", "")))

    doc.add_heading("四、推荐能力模块", level=1)
    for m in solution.get("modules", []):
        p = doc.add_paragraph()
        r = p.add_run(_clean(m.get("name", "")))
        r.bold = True
        doc.add_paragraph(f"作用：{_clean(m.get('purpose', ''))}")
        doc.add_paragraph(f"价值：{_clean(m.get('value', ''))}")

    doc.add_heading("五、场景化设计", level=1)
    for s in solution.get("scenarios", []):
        p = doc.add_paragraph()
        r = p.add_run(_clean(s.get("name", "")))
        r.bold = True
        doc.add_paragraph(_clean(s.get("description", "")))
        doc.add_paragraph(f"预期效果：{_clean(s.get('expected_effect', ''))}")

    doc.add_heading("六、实施路径", level=1)
    for item in solution.get("roadmap", []):
        p = doc.add_paragraph(style="List Bullet")
        r = p.add_run(f"{_clean(item.get('phase', ''))}：")
        r.bold = True
        p.add_run(_clean(item.get('actions', '')))

    doc.add_heading("七、投入构成", level=1)
    doc.add_paragraph(_clean(solution.get("investment", "")))
    doc.add_heading("八、预期回报", level=1)
    doc.add_paragraph(_clean(solution.get("roi", "")))
    doc.add_heading("九、为什么选择 ClassIn", level=1)
    doc.add_paragraph(_clean(solution.get("why_classin", "")))

    path = config.REPORT_DIR / f"{_safe_filename(name)}_解决方案_{time.strftime('%Y%m%d%H%M%S')}.docx"
    doc.save(path)
    return path
