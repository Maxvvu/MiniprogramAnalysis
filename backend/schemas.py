"""Pydantic 数据模型。"""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class WxLoginRequest(BaseModel):
    code: str = Field(min_length=1, description="wx.login 返回的临时登录凭证")
    nickname: str = Field(default="", max_length=64)


class TokenResponse(BaseModel):
    token: str
    user_id: int
    nickname: str
    is_admin: bool = False


class ProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=20, description="姓名/称呼")
    phone: str = Field(min_length=11, max_length=11, description="11 位手机号")


class AnalysisRequest(BaseModel):
    customer_name: str = Field(min_length=1, max_length=100, description="客户名称 / 机构名 / 教师名")
    customer_type: Literal["institution", "teacher"] = Field(
        default="institution", description="institution=教培机构 teacher=个体教师"
    )
    extra_notes: str = Field(default="", max_length=500, description="销售补充信息，可选")
    force: bool = Field(default=False, description="true=不复用缓存，强制重新分析")


class CustomerNoteRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class KnowledgeDocumentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=20, max_length=100000)
    category: str = Field(default="general", max_length=50)
    source_url: str = Field(default="", max_length=1000)


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)


# ---------- 管理后台 ----------

class AdminQuotaRequest(BaseModel):
    override: Optional[int] = Field(default=None, ge=0, le=10000, description="单人每日额度覆盖，null 表示恢复全局默认")


class AdminSettingsRequest(BaseModel):
    llm_base_url: Optional[str] = Field(default=None, max_length=200)
    llm_model: Optional[str] = Field(default=None, max_length=100)
    llm_api_key: Optional[str] = Field(default=None, max_length=200)
    daily_free_limit: Optional[int] = Field(default=None, ge=0, le=10000)
    search_enabled: Optional[bool] = None


class AdminKnowledgeStatusRequest(BaseModel):
    status: Literal["active", "archived"]


# ---------- 报告反馈闭环 ----------

class ReportFeedbackRequest(BaseModel):
    rating: Literal["useful", "needs_improvement"] = Field(
        description="useful=有用 needs_improvement=需改进"
    )
    comment: str = Field(default="", max_length=2000, description="补充或纠正信息，可选")


class AdminFeedbackAdoptRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200, description="入库标题，留空则自动生成")
    category: Optional[str] = Field(default=None, max_length=50, description="知识分类，留空默认 case")
    content: Optional[str] = Field(default=None, max_length=100000, description="入库正文，留空则由反馈自动拼装")
