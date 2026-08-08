"""分析流水线编排：行业校验 → 搜索 → 事实整理 → 销售分析 → 报告生成。

在后台线程中执行，通过 tasks 表的 status / stage 字段向前端暴露进度：
pending → screening → searching → profiling → analyzing → generating → done / failed
"""
import json
import logging

import database
from agent import llm, prompts, report, searcher

logger = logging.getLogger(__name__)


def _memory_context(memory: dict) -> str:
    lines = []
    if memory["summary"].get("summary"):
        lines.append("摘要：" + memory["summary"]["summary"])
    for fact in memory["facts"][:10]:
        lines.append("历史事实：" + fact["fact"])
    for note in memory["notes"][:6]:
        lines.append("销售跟进：" + note["content"])
    return "\n".join(lines) if lines else "（暂无既有客户记忆）"


def _knowledge_context(items: list[dict]) -> str:
    if not items:
        return "（知识库未检索到相关资料）"
    return "\n\n".join(
        f"[{item['title']}｜{item['category']}｜{item.get('source_url') or '内部资料'}]\n{item['content']}"
        for item in items
    )


def _fact_text(item: object) -> str:
    return item.get("fact", "") if isinstance(item, dict) else str(item)


def run_analysis(task_id: int) -> None:
    task = database.get_task(task_id)
    if task is None:
        return
    name = task["customer_name"]
    ctype = task["customer_type"]
    notes = task["extra_notes"] or "无"
    type_label = prompts.TYPE_LABELS.get(ctype, "教培机构")
    customer_id = task.get("customer_id")

    try:
        # 阶段 0：行业预校验（快速判断是否教育行业，非教育直接拒绝）
        database.update_task(task_id, status="running", stage="正在校验客户行业归属…")
        screen = llm.chat_json(
            prompts.SCREEN_SYSTEM,
            prompts.SCREEN_USER.format(name=name, type_label=type_label),
            temperature=0.1,
        )
        if not screen.get("is_education", False):
            # 宽容处理：检查是否有教育业务线
            education_business = screen.get("education_business", "")
            if education_business and "无" not in education_business:
                # 有教育业务线，允许通过但记录警告
                logger.warning("task=%s 非纯教育企业但有教育业务线: %s", task_id, education_business)
            else:
                # 完全无教育业务，拒绝
                industry = screen.get("industry", "未知行业")
                reason = screen.get("reason", "")
                database.update_task(
                    task_id,
                    status="failed",
                    stage="",
                    error=f"该企业不属于教育行业（{industry}），暂不支持分析。{reason}",
                )
                logger.info("task=%s 行业校验未通过: %s / %s", task_id, industry, reason)
                return
        # 从预校验结果中提取公司全称和搜索关键词，用于后续阶段精准搜索
        full_name = screen.get("full_name") or name
        search_keywords = screen.get("search_keywords", [])
        keywords_text = "；".join(search_keywords) if search_keywords else name
        logger.info("task=%s 行业校验通过: %s | 全称: %s", task_id, screen.get("education_business", ""), full_name)

        # 阶段 1：联网搜索公开信息
        database.update_task(task_id, status="running", stage="正在联网搜索客户公开信息…")
        results = searcher.search_customer(full_name, ctype)
        database.save_sources(task_id, results)
        search_context = searcher.format_search_context(results)
        memory = database.get_customer_memory(customer_id) if customer_id else {"summary": {}, "facts": [], "notes": []}
        memory_context = _memory_context(memory)
        knowledge_context = _knowledge_context(
            database.search_knowledge(f"ClassIn 企业培训 教培 {type_label} {notes}")
        )
        logger.info("task=%s 搜索到 %s 条结果", task_id, len(results))

        # 阶段 2：事实整理
        database.update_task(task_id, stage="正在整理客户事实档案…")
        profile = llm.chat_json(
            prompts.PROFILE_SYSTEM,
            prompts.PROFILE_USER.format(
                name=name, full_name=full_name, type_label=type_label, notes=notes,
                search_context=search_context,
                search_keywords=keywords_text,
                memory_context=memory_context, knowledge_context=knowledge_context,
            ),
        )

        # 兜底检查：profile 阶段二次校验是否教育行业
        identity = profile.get("identity", "")
        confidence = profile.get("confidence", "medium")
        # 教育行业关键词：如果 identity 明确提到这些，即使 confidence 低也通过（可能只是没搜到材料）
        education_keywords = ["教育", "培训", "学校", "学员", "课程", "教学", "考试", "辅导", "职教", "教培"]
        is_education_by_keywords = any(kw in identity for kw in education_keywords)
        # 明确说非教育，或 confidence 低且没有教育关键词，才拒绝
        if "非教育" in identity or (confidence == "low" and not is_education_by_keywords):
            database.update_task(
                task_id,
                status="failed",
                stage="",
                error="该企业不属于教育行业，暂不支持分析",
            )
            logger.info("task=%s profile兜底校验未通过: %s", task_id, identity)
            return

        if customer_id:
            database.add_profile_facts(
                customer_id, task_id, profile.get("facts", []), profile.get("confidence", "medium"),
                [result.get("url", "") for result in results if result.get("url")],
            )

        # 阶段 3：全套维度销售分析
        database.update_task(task_id, stage="正在进行销售导向分析…")
        analysis = llm.chat_json(
            prompts.ANALYSIS_SYSTEM,
            prompts.ANALYSIS_USER.format(
                name=name,
                full_name=full_name,
                type_label=type_label,
                notes=notes,
                profile_json=json.dumps(profile, ensure_ascii=False, indent=2),
                memory_context=memory_context,
                knowledge_context=knowledge_context,
            ),
        )

        # 向后兼容：如果 LLM 返回旧字段，自动映射到新结构
        if "competitor_guess" in analysis and "competitors" not in analysis:
            analysis["competitors"] = {
                "current_tools": [{"product": "推断：详见下方", "usage_scenario": "未知", "pain_points": ["待分析"], "replacement_opportunity": "medium"}],
                "switch_barriers": analysis.get("competitor_guess", ""),
                "coexist_strategy": "待分析"
            }
        if isinstance(analysis.get("growth"), str):
            # 旧格式是纯文本，包装成新结构
            analysis["growth"] = {
                "current_scale": "未知",
                "growth_rate": "未知",
                "expansion_actions": ["（旧数据格式，详见下方文本）"],
                "increment_drivers": ["待重新分析"],
                "timing_window": {"best_timing": "待确认", "urgency": "medium", "reason": "旧数据需重新分析"},
                "potential_value": "待评估",
                "_legacy_text": analysis["growth"]
            }

        # 阶段 4：生成内部分析报告
        database.update_task(task_id, stage="正在生成 Word 报告…")
        markdown = report.render_markdown(name, ctype, analysis, profile)
        docx_path = report.generate_docx(name, ctype, analysis, profile)

        # 阶段 5：生成面向客户的个性化解决方案
        database.update_task(task_id, stage="正在生成个性化解决方案…")
        solution = llm.chat_json(
            prompts.SOLUTION_SYSTEM,
            prompts.SOLUTION_USER.format(
                name=name,
                type_label=type_label,
                analysis_json=json.dumps(analysis, ensure_ascii=False, indent=2),
            ),
        )
        solution_md = report.render_solution_markdown(name, solution)
        solution_path = report.generate_solution_docx(name, solution)
        solution["docx_name"] = solution_path.name

        database.update_task(
            task_id,
            status="done",
            stage="",
            report_json={
                "analysis": analysis,
                "profile": profile,
                "docx_name": docx_path.name,
                "solution": solution,
                "solution_md": solution_md,
            },
            report_md=markdown,
        )
        if customer_id:
            facts = [_fact_text(item) for item in profile.get("facts", [])]
            summary = "\n".join([
                f"最近结论：{analysis.get('summary', '')}",
                "已收集事实：" + "；".join(facts[:5]),
                "待确认：" + "；".join(profile.get("unknowns", [])[:3]),
            ])
            database.upsert_memory_summary(customer_id, summary)
        logger.info("task=%s 分析完成 -> %s / %s", task_id, docx_path, solution_path)
    except Exception as exc:  # noqa: BLE001
        logger.exception("task=%s 分析失败", task_id)
        database.update_task(task_id, status="failed", stage="", error=str(exc))
