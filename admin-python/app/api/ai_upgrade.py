"""AI 前沿技术自动升级 API"""
from fastapi import APIRouter, HTTPException

from app.services.ai_upgrade_service import ai_upgrade_service

router = APIRouter(prefix="/ai-upgrade", tags=["AI自动升级"])


@router.post("/run")
async def run_daily_upgrade():
    """手动触发每日 AI 升级分析"""
    try:
        result = await ai_upgrade_service.run_daily_upgrade()
        return {"code": 200, "message": "AI 升级分析完成", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_upgrade_status():
    """获取最近一次升级分析状态"""
    try:
        # 从知识库查询最近的升级报告
        from app.core.database import async_session_maker
        from app.models.agent_models import AgentKnowledge
        from sqlalchemy import select

        async with async_session_maker() as session:
            result = await session.execute(
                select(AgentKnowledge)
                .where(AgentKnowledge.category == "ai_upgrade", AgentKnowledge.is_deleted == 0)
                .order_by(AgentKnowledge.create_time.desc())
                .limit(1)
            )
            latest = result.scalar_one_or_none()

            if latest:
                return {
                    "code": 200,
                    "message": "查询成功",
                    "data": {
                        "knowledge_id": latest.knowledge_id,
                        "title": latest.title,
                        "last_run": latest.create_time,
                        "version": latest.version,
                    },
                }
            return {"code": 200, "message": "尚未运行过升级分析", "data": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_upgrade_history():
    """获取升级分析历史"""
    try:
        from app.core.database import async_session_maker
        from app.models.agent_models import AgentKnowledge
        from sqlalchemy import select

        async with async_session_maker() as session:
            result = await session.execute(
                select(AgentKnowledge)
                .where(AgentKnowledge.category == "ai_upgrade", AgentKnowledge.is_deleted == 0)
                .order_by(AgentKnowledge.create_time.desc())
                .limit(30)
            )
            records = result.scalars().all()

            return {
                "code": 200,
                "message": "查询成功",
                "data": [
                    {
                        "knowledge_id": r.knowledge_id,
                        "title": r.title,
                        "create_time": r.create_time,
                        "version": r.version,
                    }
                    for r in records
                ],
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
