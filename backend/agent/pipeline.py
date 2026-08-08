"""分析流水线：拆分为独立阶段，支持断点续跑和真实取消。

阶段顺序：screen → search → profile → analyze → report → solution
每个阶段将中间结果持久化到 tasks.stage_data，失败时可从断点恢复。
"""
import json
import logging

import config
import database
from agent import llm, prompts, report, searcher

logger = logging.getLogger(__name__)

STAGES = ["screen", "search", "profile", "analyze", "report", "solution"]


def _memory_context(memory: dict) -> str:
    lines = []
    if memory["summary"].get("summary"):
        lines.append("摘要：" + memory["summary"]["summary"])
    for fact in memory["facts"][: config.MEMORY_MAX_FACTS]:
        lines.append("历史事实：" + fact["fact"])
    for note in memory["notes"][: config.MEMORY_MAX_NOTES]:
        lines.append("销售跟进：" + note["content"])
    return "\n".join(lines) if lines else "（暂无既有客户记忆）"


def _knowledge_context(items: list[dict]) -> str:
    """拼接知识库检索结果：去重 + 条数/单条/总量三重上限，控制注入体量与噪声。"""
    if not items:
        return "（知识库未检索到相关资料）"
    seen: set = set()
    blocks: list[str] = []
    total = 0
    for item in items[: config.KNOWLEDGE_MAX_ITEMS]:
        content = (item.get("content") or "").strip()
        if not content:
            continue
        # 去重：同一文档的重复切片或完全相同的内容只保留一次
        dedup_key = (item.get("title", ""), content[:80])
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        content = searcher.truncate_text(content, config.KNOWLEDGE_ITEM_MAX_CHARS)
        block = (
            f"[{item['title']}｜{item['category']}｜{item.get('source_url') or '内部资料'}]\n{content}"
        )
        if blocks and total + len(block) > config.KNOWLEDGE_CONTEXT_MAX_CHARS:
            break
        blocks.append(block)
        total += len(block)
    return "\n\n".join(blocks) if blocks else "（知识库未检索到相关资料）"


def _fact_text(item: object) -> str:
    return item.get("fact", "") if isinstance(item, dict) else str(item)


def stage_screen(task_id: int, task: dict, prev_data: dict) -> dict:
    """阶段 0：行业预校验（快速判断是否教育行业，非教育直接拒绝）。"""
    name = task["customer_name"]
    ctype = task["customer_type"]
    type_label = prompts.TYPE_LABELS.get(ctype, "教培机构")

    database.update_task(task_id, stage="正在校验客户行业归属…")
    screen = llm.chat_json(
        prompts.SCREEN_SYSTEM,
        prompts.SCREEN_USER.format(name=name, type_label=type_label),
        temperature=0.1,
    )

    if not screen.get("is_education", False):
        education_business = screen.get("education_business", "")
        if education_business and "无" not in education_business:
            logger.warning("task=%s 非纯教育企业但有教育业务线: %s", task_id, education_business)
        else:
            industry = screen.get("industry", "未知行业")
            reason = screen.get("reason", "")
            database.update_task(
                task_id,
                status="failed",
                stage="",
                error=f"该企业不属于教育行业（{industry}），暂不支持分析。{reason}",
            )
            logger.info("task=%s 行业校验未通过: %s / %s", task_id, industry, reason)
            return {"stopped": True}

    full_name = screen.get("full_name") or name
    search_keywords = screen.get("search_keywords", [])
    logger.info("task=%s 行业校验通过: %s | 全称: %s", task_id, screen.get("education_business", ""), full_name)

    return {
        "full_name": full_name,
        "search_keywords": search_keywords,
        "education_business": screen.get("education_business", ""),
    }


def stage_search(task_id: int, task: dict, prev_data: dict) -> dict:
    """阶段 1：联网搜索公开信息。"""
    customer_id = task.get("customer_id")
    ctype = task["customer_type"]
    notes = task["extra_notes"] or "无"
    type_label = prompts.TYPE_LABELS.get(ctype, "教培机构")
    full_name = prev_data["full_name"]
    search_keywords = prev_data.get("search_keywords", [])

    database.update_task(task_id, stage="正在联网搜索客户公开信息…")
    results = searcher.search_customer(full_name, ctype, keywords=search_keywords)
    database.save_sources(task_id, results)
    search_context = searcher.format_search_context(results)

    memory = database.get_customer_memory(customer_id) if customer_id else {"summary": {}, "facts": [], "notes": []}
    memory_context = _memory_context(memory)
    knowledge_context = _knowledge_context(
        database.search_knowledge(f"ClassIn 企业培训 教培 {type_label} {notes}")
    )
    logger.info("task=%s 搜索到 %s 条结果", task_id, len(results))

    return {
        "search_results": results,
        "search_context": search_context,
        "memory": memory,
        "memory_context": memory_context,
        "knowledge_context": knowledge_context,
    }


def stage_profile(task_id: int, task: dict, prev_data: dict) -> dict:
    """阶段 2：事实整理。"""
    name = task["customer_name"]
    ctype = task["customer_type"]
    notes = task["extra_notes"] or "无"
    type_label = prompts.TYPE_LABELS.get(ctype, "教培机构")
    customer_id = task.get("customer_id")
    full_name = prev_data["full_name"]
    search_keywords = prev_data["search_keywords"]
    keywords_text = "；".join(search_keywords) if search_keywords else name
    search_context = prev_data["search_context"]
    memory_context = prev_data["memory_context"]
    knowledge_context = prev_data["knowledge_context"]

    database.update_task(task_id, stage="正在整理客户事实档案…")
    profile = llm.chat_json_cheap_first(
        prompts.PROFILE_SYSTEM,
        prompts.PROFILE_USER.format(
            name=name, full_name=full_name, type_label=type_label, notes=notes,
            search_context=search_context,
            search_keywords=keywords_text,
            memory_context=memory_context, knowledge_context=knowledge_context,
        ),
        enable_search=False,
    )

    identity = profile.get("identity", "")
    confidence = profile.get("confidence", "medium")
    education_keywords = ["教育", "培训", "学校", "学员", "课程", "教学", "考试", "辅导", "职教", "教培"]
    is_education_by_keywords = any(kw in identity for kw in education_keywords)
    if "非教育" in identity or (confidence == "low" and not is_education_by_keywords):
        database.update_task(
            task_id,
            status="failed",
            stage="",
            error="该企业不属于教育行业，暂不支持分析",
        )
        logger.info("task=%s profile兜底校验未通过: %s", task_id, identity)
        return {"stopped": True}

    if customer_id:
        search_results = prev_data["search_results"]
        database.add_profile_facts(
            customer_id, task_id, profile.get("facts", []), profile.get("confidence", "medium"),
            [result.get("url", "") for result in search_results if result.get("url")],
        )

    return {"profile": profile}


def stage_analyze(task_id: int, task: dict, prev_data: dict) -> dict:
    """阶段 3：全套维度销售分析。"""
    name = task["customer_name"]
    ctype = task["customer_type"]
    notes = task["extra_notes"] or "无"
    type_label = prompts.TYPE_LABELS.get(ctype, "教培机构")
    full_name = prev_data["full_name"]
    profile = prev_data["profile"]
    memory_context = prev_data["memory_context"]
    knowledge_context = prev_data["knowledge_context"]

    database.update_task(task_id, stage="正在进行销售导向分析…")
    from datetime import datetime, timedelta, timezone
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y年%m月%d日")
    analysis = llm.chat_json(
        prompts.ANALYSIS_SYSTEM,
        prompts.ANALYSIS_USER.format(
            today=today,
            name=name,
            full_name=full_name,
            type_label=type_label,
            notes=notes,
            profile_json=json.dumps(profile, ensure_ascii=False, indent=2),
            memory_context=memory_context,
            knowledge_context=knowledge_context,
        ),
        temperature=0.2,
        enable_search=False,
    )

    if "competitor_guess" in analysis and "competitors" not in analysis:
        analysis["competitors"] = {
            "current_tools": [{"product": "推断：详见下方", "usage_scenario": "未知", "is_inference": True, "pain_points": ["待分析"], "replacement_opportunity": "medium", "basis": "旧数据格式"}],
            "switch_barriers": analysis.get("competitor_guess", ""),
            "coexist_strategy": "待分析"
        }
    if isinstance(analysis.get("growth"), str):
        analysis["growth"] = {
            "current_scale": "未知",
            "growth_rate": "未知",
            "expansion_actions": [{"action": "（旧数据格式，详见下方文本）", "is_inference": True, "basis": "旧数据", "confidence": "low"}],
            "increment_drivers": [{"driver": "待重新分析", "is_inference": True, "basis": "待分析", "confidence": "low"}],
            "timing_window": {"best_timing": "待确认", "urgency": "medium", "reason": "旧数据需重新分析"},
            "potential_value": "待评估",
            "_legacy_text": analysis["growth"]
        }
    # 兼容旧格式：如果 expansion_actions/increment_drivers 是字符串数组，转换为对象数组
    if isinstance(analysis.get("growth", {}).get("expansion_actions"), list) and analysis["growth"]["expansion_actions"]:
        if isinstance(analysis["growth"]["expansion_actions"][0], str):
            analysis["growth"]["expansion_actions"] = [
                {"action": item, "is_inference": False, "basis": "搜索事实", "confidence": "medium"}
                for item in analysis["growth"]["expansion_actions"]
            ]
    if isinstance(analysis.get("growth", {}).get("increment_drivers"), list) and analysis["growth"]["increment_drivers"]:
        if isinstance(analysis["growth"]["increment_drivers"][0], str):
            analysis["growth"]["increment_drivers"] = [
                {"driver": item, "is_inference": False, "basis": "搜索事实", "confidence": "medium"}
                for item in analysis["growth"]["increment_drivers"]
            ]
    # 兼容旧格式：如果 current_tools 没有 is_inference 字段，添加默认值
    if isinstance(analysis.get("competitors", {}).get("current_tools"), list):
        for tool in analysis["competitors"]["current_tools"]:
            if isinstance(tool, dict) and "is_inference" not in tool:
                tool["is_inference"] = False
                tool["basis"] = "未标注"

    return {"analysis": analysis}


def stage_report(task_id: int, task: dict, prev_data: dict) -> dict:
    """阶段 4：生成内部分析报告。"""
    name = task["customer_name"]
    ctype = task["customer_type"]
    profile = prev_data["profile"]
    analysis = prev_data["analysis"]

    database.update_task(task_id, stage="正在生成 Word 报告…")
    markdown = report.render_markdown(name, ctype, analysis, profile)
    docx_path = report.generate_docx(name, ctype, analysis, profile)

    return {"markdown": markdown, "docx_name": docx_path.name}


def stage_solution(task_id: int, task: dict, prev_data: dict) -> dict:
    """阶段 5：生成面向客户的个性化解决方案。"""
    name = task["customer_name"]
    ctype = task["customer_type"]
    type_label = prompts.TYPE_LABELS.get(ctype, "教培机构")
    analysis = prev_data["analysis"]
    customer_id = task.get("customer_id")
    profile = prev_data["profile"]

    database.update_task(task_id, stage="正在生成个性化解决方案…")
    solution = llm.chat_json(
        prompts.SOLUTION_SYSTEM,
        prompts.SOLUTION_USER.format(
            name=name,
            type_label=type_label,
            analysis_json=json.dumps(analysis, ensure_ascii=False, indent=2),
        ),
        enable_search=False,
    )
    solution_md = report.render_solution_markdown(name, solution)
    solution_path = report.generate_solution_docx(name, solution)
    solution["docx_name"] = solution_path.name

    report_data = {
        "analysis": analysis,
        "profile": profile,
        "docx_name": prev_data["docx_name"],
        "solution": solution,
        "solution_md": solution_md,
    }
    database.update_task(
        task_id,
        status="done",
        stage="",
        report_json=report_data,
        report_md=prev_data["markdown"],
    )

    if customer_id:
        facts = [_fact_text(item) for item in profile.get("facts", [])]
        summary = "\n".join([
            f"最近结论：{analysis.get('summary', '')}",
            "已收集事实：" + "；".join(facts[:5]),
            "待确认：" + "；".join(profile.get("unknowns", [])[:3]),
        ])
        database.upsert_memory_summary(customer_id, summary)

    logger.info("task=%s 分析完成 -> %s / %s", task_id, prev_data["docx_name"], solution_path)
    return {"final": True}


STAGE_FUNCS = [stage_screen, stage_search, stage_profile, stage_analyze, stage_report, stage_solution]


def run_task(task_id: int) -> None:
    """执行任务：从 stage_index 开始依次运行各阶段，支持断点续跑和取消检测。"""
    task = database.get_task(task_id)
    if task is None:
        return

    stage_index = task.get("stage_index", 0) or 0
    stage_data = database.get_stage_data(task_id)

    # 续跑时重建扁平键：已完成阶段的结果此前仅在内存合并，持久化里只有编号键（"0"/"1"/…），
    # 需按顺序把它们摊平回 stage_data，后续阶段才能读到 full_name/profile 等依赖字段。
    for idx in range(stage_index):
        prev_result = stage_data.get(str(idx))
        if isinstance(prev_result, dict):
            for key, value in prev_result.items():
                stage_data[key] = value

    try:
        for i in range(stage_index, len(STAGE_FUNCS)):
            if database.is_task_cancelled(task_id):
                logger.info("task=%s 已被用户取消", task_id)
                return

            stage_func = STAGE_FUNCS[i]
            logger.info("task=%s 进入阶段 %d/%d: %s", task_id, i + 1, len(STAGE_FUNCS), STAGES[i])

            result = stage_func(task_id, task, stage_data)

            if result.get("stopped"):
                logger.info("task=%s 阶段 %s 主动终止", task_id, STAGES[i])
                return

            stage_data[str(i)] = result
            database.set_stage_data(task_id, i, result)

            # 合并结果到 stage_data 供后续阶段使用
            for key, value in result.items():
                stage_data[key] = value

    except Exception as exc:
        logger.exception("task=%s 分析失败", task_id)
        database.update_task(task_id, status="failed", stage="", error=f"阶段执行失败: {type(exc).__name__}")
