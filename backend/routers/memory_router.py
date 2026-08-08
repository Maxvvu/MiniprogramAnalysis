"""客户长期记忆和团队知识库接口。"""
from fastapi import APIRouter, Depends, HTTPException

import auth
import database
import schemas

router = APIRouter(prefix="/api", tags=["memory"])


def _customer_view(customer: dict) -> dict:
    memory = database.get_customer_memory(customer["id"])
    return {**customer, "memory": memory}


@router.get("/customers")
def list_customers(user: dict = Depends(auth.get_current_user)):
    return {"items": database.list_customers(user["id"])}


@router.get("/customers/{customer_id}")
def get_customer(customer_id: int, user: dict = Depends(auth.get_current_user)):
    customer = database.get_customer(customer_id, user["id"])
    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")
    return _customer_view(customer)


@router.post("/customers/{customer_id}/notes")
def add_note(customer_id: int, body: schemas.CustomerNoteRequest, user: dict = Depends(auth.get_current_user)):
    if not database.get_customer(customer_id, user["id"]):
        raise HTTPException(status_code=404, detail="客户不存在")
    return database.add_customer_note(customer_id, user["id"], body.content)


@router.post("/knowledge/documents")
def create_document(body: schemas.KnowledgeDocumentRequest, user: dict = Depends(auth.get_current_user)):
    return database.create_knowledge_document(user["id"], body.title, body.content, body.category, body.source_url)


@router.post("/knowledge/search")
def search_knowledge(body: schemas.KnowledgeSearchRequest, user: dict = Depends(auth.get_current_user)):
    # 当前知识库为团队共享资料；正式多团队部署时应在这里加入组织与角色过滤。
    return {"items": database.search_knowledge(body.query)}
