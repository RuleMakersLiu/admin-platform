"""激活体验API路由"""
from typing import AsyncGenerator
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.activation import (
    ActivationStartRequest,
    ActivationStartResponse,
    TemplatesResponse,
    TemplateItem,
    ActivationChatRequest,
    ActivationCompleteRequest,
    ActivationCompleteResponse,
    ActivationStatus,
)
from app.schemas.common import Response
from app.services.activation_service import activation_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/activation", tags=["激活体验"])


@router.post("/start", response_model=Response)
async def start_activation(
    request: ActivationStartRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    开始激活流程
    
    - 创建激活会话
    - 预热AI连接
    - 返回欢迎消息和建议提示词
    """
    try:
        # 启动激活会话
        session = await activation_service.start_activation(
            user_id=request.user_id,
            tenant_id=request.tenant_id,
            user_name=request.user_name,
        )
        
        # 获取欢迎消息和建议提示词
        welcome_message = activation_service.get_welcome_message(
            session.user_name
        )
        suggested_prompts = activation_service.get_suggested_prompts()
        
        response_data = ActivationStartResponse(
            activation_id=session.activation_id,
            status=session.status,
            welcome_message=welcome_message,
            suggested_prompts=suggested_prompts,
        )
        
        return Response(data=response_data.model_dump(by_alias=True))
        
    except Exception as e:
        logger.error(f"❌ 启动激活流程失败: {e}")
        return Response(code=500, message=f"启动失败: {str(e)}")


@router.get("/templates", response_model=Response)
async def get_templates():
    """
    获取演示模板
    
    - 返回预定义的演示模板
    - 按分类组织
    """
    try:
        templates, categories = await activation_service.get_templates()
        
        template_items = [
            TemplateItem(**t) for t in templates
        ]
        
        response_data = TemplatesResponse(
            templates=template_items,
            categories=categories,
        )
        
        return Response(data=response_data.model_dump())
        
    except Exception as e:
        logger.error(f"❌ 获取模板失败: {e}")
        return Response(code=500, message=f"获取模板失败: {str(e)}")


@router.post("/chat")
async def activation_chat(
    request: ActivationChatRequest,
):
    """
    激活对话（支持SSE流式响应）
    
    - 使用Server-Sent Events (SSE)流式返回AI响应
    - 减少首字延迟，提升用户体验
    """
    # 验证会话
    session = activation_service.get_session(request.activation_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="激活会话不存在或已过期"
        )
    
    if request.use_stream:
        # SSE流式响应
        async def generate() -> AsyncGenerator[str, None]:
            async for chunk in activation_service.chat_stream(
                request.activation_id,
                request.message,
            ):
                yield chunk
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # 禁用Nginx缓冲
            }
        )
    else:
        # 非流式响应（收集完整响应后返回）
        full_response = ""
        async for chunk in activation_service.chat_stream(
            request.activation_id,
            request.message,
        ):
            if chunk.startswith("data: "):
                import json
                try:
                    data = json.loads(chunk[6:].strip())
                    if data.get("type") == "chunk":
                        full_response += data.get("content", "")
                    elif data.get("type") == "done":
                        break
                except:
                    pass
        
        return Response(data={"reply": full_response})


@router.post("/complete", response_model=Response)
async def complete_activation(
    request: ActivationCompleteRequest,
):
    """
    完成激活流程
    
    - 标记激活为已完成
    - 记录用户评分和反馈
    - 返回后续步骤建议
    """
    try:
        result = await activation_service.complete_activation(
            activation_id=request.activation_id,
            rating=request.rating,
            feedback=request.feedback,
        )
        
        response_data = ActivationCompleteResponse(**result)
        return Response(data=response_data.model_dump(by_alias=True))
        
    except Exception as e:
        logger.error(f"❌ 完成激活失败: {e}")
        return Response(code=500, message=f"完成激活失败: {str(e)}")


@router.get("/status/{activation_id}", response_model=Response)
async def get_activation_status(activation_id: str):
    """
    获取激活状态
    
    - 查看激活会话的当前状态
    - 返回消息数量、活动时间等信息
    """
    session = activation_service.get_session(activation_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="激活会话不存在或已过期"
        )
    
    status_data = ActivationStatus(
        activation_id=session.activation_id,
        status=session.status,
        message_count=session.message_count,
        started_at=session.started_at,
        last_activity=session.last_activity,
    )
    
    return Response(data=status_data.model_dump(by_alias=True))


# ==================== 登录时预热接口 ====================

@router.post("/warmup", response_model=Response)
async def warmup_ai():
    """
    预热AI连接（登录时调用）
    
    - 提前建立AI连接
    - 减少首次对话的延迟
    - 建议在登录成功后立即调用
    """
    try:
        success = await activation_service.warmup()
        
        if success:
            return Response(
                data={"status": "warmed", "message": "AI连接已预热"},
                message="预热成功"
            )
        else:
            return Response(
                code=500,
                message="预热失败，但不影响后续使用"
            )
            
    except Exception as e:
        logger.error(f"❌ AI预热失败: {e}")
        return Response(code=500, message=f"预热失败: {str(e)}")
