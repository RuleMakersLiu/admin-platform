"""API路由汇总"""
from fastapi import APIRouter

from app.api.v1 import activation, agent, auth, system, tenant
from app.api.flow import router as flow_router
from app.api.kanban import router as kanban_router
from app.api.agents import router as agents_router
from app.api.tasks import router as tasks_router
from app.api.ai_upgrade import router as ai_upgrade_router
from app.api.knowledge import router as knowledge_router
from app.api.skills import router as skills_router
from app.api.chat import router as chat_router
from app.messaging.api import router as messaging_router

api_router = APIRouter()

# 注册各模块路由
api_router.include_router(auth.router)
api_router.include_router(activation.router)  # 激活体验路由
api_router.include_router(agent.router)
api_router.include_router(system.router)
api_router.include_router(tenant.router)
api_router.include_router(flow_router)  # 智能体流程路由
api_router.include_router(kanban_router)  # 看板管理路由
api_router.include_router(agents_router)  # 智能体状态路由
api_router.include_router(tasks_router)  # 任务管理路由
api_router.include_router(messaging_router)  # 多渠道消息路由
api_router.include_router(ai_upgrade_router)  # AI自动升级路由
api_router.include_router(knowledge_router)  # 知识库管理路由
api_router.include_router(skills_router)  # Skills技能系统路由
api_router.include_router(chat_router)  # 流式聊天路由
