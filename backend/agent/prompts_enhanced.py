"""增强版 Prompt 示例 - 更结构化的增量分析

这是对原有 prompts.py 的改进建议，展示如何让分析更聚焦、更可操作。
"""

# 增强版分析输出结构
ANALYSIS_USER_ENHANCED = """
客户名称：{name}
全称/补全名称：{full_name}
客户类型：{type_label}
销售补充信息：{notes}

客户事实档案（上一阶段整理）：
{profile_json}

该客户既有记忆：
{memory_context}

可引用的 ClassIn 内部知识资料：
{knowledge_context}

请输出 JSON（所有字段必填）：
{{
  "summary": "3 句话以内的客户总览与销售结论",
  "overview": "客户概况：定位、规模、区域、成立时间、业务构成",
  "business_model": "业务模式与主打产品：收入来源、客群、定价特点",

  "growth": {{
    "current_scale": "当前规模：校区数/学员数/年营收（能确认的数字）",
    "growth_rate": "近 1-2 年增长率（如有数据）或'未知'",
    "expansion_actions": ["近 6 个月的扩张动作：开新校区、新业务线、融资、并购等"],
    "increment_drivers": ["未来 1-2 年的增量来源：新校区、新产品线、学员扩招等"],
    "timing_window": {{
      "best_timing": "最佳切入时间（如：Q3 新校区开业前/融资后扩张期）",
      "urgency": "需求紧迫度（high/medium/low）",
      "reason": "判断依据"
    }},
    "potential_value": "ClassIn 在增量场景中的年付费潜力区间（如 8-15 万）"
  }},

  "revenue_payment": "营收与付费能力：营收规模（可估算，注明依据）、现金流特点、预算敏感度",
  "digitalization": "数字化与在线教学现状：现有工具、线上化程度、明显的痛点或空白",

  "competitors": {{
    "current_tools": [
      {{
        "product": "产品名称（如钉钉、腾讯会议、小鹅通等）",
        "usage_scenario": "使用场景",
        "pain_points": ["该工具的明显痛点"],
        "replacement_opportunity": "high / medium / low（替换机会）"
      }}
    ],
    "switch_barriers": "替换成本与风险分析",
    "coexist_strategy": "如果无法替换，与现有工具共存的切入点"
  }},

  "ka_rating": {{
    "level": "S / A / B / C",
    "reason": "分级理由（对照分级标准）",
    "annual_potential": "预估年付费潜力（区间，如 10-20 万）"
  }},

  "sales_direction": {{
    "entry_points": [
      {{
        "priority": 1,
        "point": "切入点描述",
        "why_effective": "为什么有效（结合客户具体场景）",
        "success_rate": "high / medium / low",
        "estimated_value": "该场景预估单值（如首单 5-8 万）"
      }}
    ],
    "first_actions": ["建议的首次接触动作与沟通要点（开场白方向）"],
    "objections": [
      {{"objection": "客户最可能提出的异议", "response": "应对话术方向"}}
    ]
  }},

  "competitive_intel": {{
    "peer_comparison": "与同类机构对比（规模、模式、数字化程度）",
    "market_position": "在区域/细分市场的地位",
    "threat_level": "high / medium / low（竞对跟进该客户的可能性）"
  }},

  "risks": "跟进该客户的风险与注意事项",

  "confidence": {{
    "overall": "high / medium / low（整体分析置信度）",
    "search_quality": "搜索信息质量评估",
    "data_completeness": "关键数据完整度（营收/规模/增长等）",
    "inference_ratio": "推断占比（事实 20%、行业常识推断 80%）",
    "recommendation": "建议：如'高置信度可直接跟进'或'建议先电话沟通确认规模数据'"
  }},

  "info_note": "信息来源说明：哪些来自搜索事实、哪些是行业推断，置信度如何"
}}

【重要提示】
1. growth.increment_drivers 和 growth.timing_window 是销售最关心的，必须具体分析
2. competitors.current_tools 至少列出 2-3 个可能的工具，即使是推断也要基于行业常识
3. sales_direction.entry_points 按优先级排序，priority=1 的是最推荐的
4. confidence 字段帮助销售判断是否需要补充调研
"""

# 改进后的搜索关键词生成
SCREEN_USER_ENHANCED = """
客户名称：{name}
客户类型：{type_label}

请联网搜索该公司，判断其是否属于教育行业。
如果客户名称是简称或模糊名称（如"好未来""新东方"），请先补全为该公司的全称（如"好未来教育科技集团（TAL Education Group）"），
再基于全称搜索判断。

请输出 JSON：
{{
  "is_education": true/false,
  "full_name": "该公司的全称（含曾用名、英文名、上市代码等，如无法确认则填原始名称）",
  "search_keywords": [
    "推荐的精准搜索关键词，用于后续深度搜索，5-8 个",
    "示例：好未来教育、学而思、营收、校区数量、学员规模、融资情况、在线课程平台"
  ],
  "industry": "该公司的主要行业领域",
  "education_business": "教育相关业务描述（如果没有则填'无'）",
  "business_scale_hint": "如果能从搜索中初步判断规模（大型/中型/小型），在此说明，否则填'未知'",
  "reason": "判断依据，简述"
}}

【搜索关键词生成提示】
- 包含公司全称、简称、品牌名
- 包含规模相关词：营收、融资、校区、学员数、估值
- 包含业务相关词：课程、培训、教学、直播、在线教育
- 包含增长相关词：扩张、开店、新业务
"""
