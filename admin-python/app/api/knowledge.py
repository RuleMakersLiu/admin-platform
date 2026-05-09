"""知识库管理 API"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, List

from app.services.knowledge_service import knowledge_service

router = APIRouter(prefix="/knowledge", tags=["知识库管理"])


def _get_tenant_id(request: Request) -> int:
    try:
        return int(request.headers.get("X-Tenant-Id", "1"))
    except (ValueError, TypeError):
        return 1


# ---- Request Models ----

class CreateKnowledgeRequest(BaseModel):
    title: str = Field(min_length=1, description="知识标题")
    content: str = Field(min_length=1, description="知识内容")
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    source: Optional[str] = None
    project_id: Optional[int] = None


class UpdateKnowledgeRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    source: Optional[str] = None


class CreateEdgeRequest(BaseModel):
    source_id: str
    target_id: str
    relation_type: str = "related_to"
    weight: float = 1.0
    description: Optional[str] = None


# ---- Fixed-path routes MUST come before /{knowledge_id} ----

@router.post("/create")
async def create_knowledge(req: CreateKnowledgeRequest, http_request: Request):
    """创建知识条目"""
    tenant_id = _get_tenant_id(http_request)
    knowledge = await knowledge_service.create_knowledge(
        title=req.title,
        content=req.content,
        tenant_id=tenant_id,
        category=req.category,
        tags=req.tags,
        source=req.source,
        project_id=req.project_id,
    )
    return {"code": 200, "message": "创建成功", "data": {"knowledge_id": knowledge.knowledge_id}}


@router.get("/search/list")
async def search_knowledge(
    http_request: Request,
    query: str = "",
    category: Optional[str] = None,
    tags: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
):
    """搜索知识库"""
    tenant_id = _get_tenant_id(http_request)
    tag_list = tags.split(",") if tags else None
    result = await knowledge_service.search_knowledge(
        query=query,
        tenant_id=tenant_id,
        category=category,
        tags=tag_list,
        limit=limit,
        offset=offset,
    )
    return {"code": 200, "data": result}


@router.get("/meta/categories")
async def list_categories(http_request: Request):
    """列出所有分类"""
    tenant_id = _get_tenant_id(http_request)
    categories = await knowledge_service.list_categories(tenant_id)
    return {"code": 200, "data": categories}


@router.get("/meta/tags")
async def list_tags(http_request: Request):
    """列出所有标签"""
    tenant_id = _get_tenant_id(http_request)
    tags = await knowledge_service.list_tags(tenant_id)
    return {"code": 200, "data": tags}


@router.get("/stats")
async def get_stats(http_request: Request):
    """知识库统计"""
    tenant_id = _get_tenant_id(http_request)
    stats = await knowledge_service.get_stats(tenant_id)
    return {"code": 200, "data": stats}


@router.post("/graph/edge")
async def create_edge(req: CreateEdgeRequest, http_request: Request):
    """创建知识图谱关联"""
    tenant_id = _get_tenant_id(http_request)
    edge = await knowledge_service.create_edge(
        source_id=req.source_id,
        target_id=req.target_id,
        relation_type=req.relation_type,
        tenant_id=tenant_id,
        weight=req.weight,
        description=req.description,
    )
    return {"code": 200, "message": "关联创建成功", "data": {"edge_id": edge.edge_id}}


@router.delete("/graph/edge/{edge_id}")
async def delete_edge(edge_id: str):
    """删除知识图谱关联"""
    ok = await knowledge_service.delete_edge(edge_id)
    if not ok:
        raise HTTPException(status_code=404, detail="关联不存在")
    return {"code": 200, "message": "删除成功"}


@router.get("/graph/view")
async def get_graph(
    http_request: Request,
    category: Optional[str] = None,
    max_nodes: int = 50,
):
    """获取知识图谱"""
    tenant_id = _get_tenant_id(http_request)
    graph = await knowledge_service.get_graph(
        tenant_id=tenant_id,
        category=category,
        max_nodes=max_nodes,
    )
    return {"code": 200, "data": graph}


# ---- Dynamic-path routes come LAST ----

@router.get("/graph/related/{knowledge_id}")
async def get_related(
    knowledge_id: str,
    relation_type: Optional[str] = None,
    direction: str = "both",
    limit: int = 20,
):
    """获取相关知识"""
    edges = await knowledge_service.get_related(
        knowledge_id=knowledge_id,
        relation_type=relation_type,
        direction=direction,
        limit=limit,
    )
    return {"code": 200, "data": edges}


@router.post("/graph/auto-link/{knowledge_id}")
async def auto_link(knowledge_id: str, http_request: Request):
    """自动关联知识"""
    tenant_id = _get_tenant_id(http_request)
    count = await knowledge_service.auto_link(knowledge_id, tenant_id)
    return {"code": 200, "message": f"已创建 {count} 条关联", "data": {"count": count}}


@router.get("/{knowledge_id}")
async def get_knowledge(knowledge_id: str):
    """获取知识详情"""
    knowledge = await knowledge_service.get_knowledge(knowledge_id)
    if not knowledge:
        raise HTTPException(status_code=404, detail="知识不存在")
    import json
    return {
        "code": 200,
        "data": {
            "knowledge_id": knowledge.knowledge_id,
            "title": knowledge.title,
            "content": knowledge.content,
            "category": knowledge.category,
            "tags": json.loads(knowledge.tags) if knowledge.tags else [],
            "source": knowledge.source,
            "version": knowledge.version,
            "view_count": knowledge.view_count,
            "create_time": knowledge.create_time,
            "update_time": knowledge.update_time,
        },
    }


@router.put("/{knowledge_id}")
async def update_knowledge(knowledge_id: str, req: UpdateKnowledgeRequest):
    """更新知识条目"""
    knowledge = await knowledge_service.update_knowledge(
        knowledge_id=knowledge_id,
        title=req.title,
        content=req.content,
        category=req.category,
        tags=req.tags,
        source=req.source,
    )
    if not knowledge:
        raise HTTPException(status_code=404, detail="知识不存在")
    return {"code": 200, "message": "更新成功"}


@router.delete("/{knowledge_id}")
async def delete_knowledge(knowledge_id: str):
    """删除知识条目"""
    ok = await knowledge_service.delete_knowledge(knowledge_id)
    if not ok:
        raise HTTPException(status_code=404, detail="知识不存在")
    return {"code": 200, "message": "删除成功"}
