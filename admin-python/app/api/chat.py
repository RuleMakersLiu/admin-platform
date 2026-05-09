"""流式聊天 API - SSE + WebSocket"""
import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.ai.agents import AgentService, AgentType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["AI 聊天"])

_agent_service = AgentService()


class ChatRequest(BaseModel):
    message: str = Field(..., description="用户消息")
    session_id: Optional[str] = Field(default=None, description="会话ID，不传则创建新会话")
    agent_type: str = Field(default="PM", description="Agent 类型: PM, PJM, BE, FE, QA, RPT")


class ChatResponse(BaseModel):
    session_id: str
    msg_id: str
    agent_type: str
    reply: str
    msg_type: str = "chat"


# ==================== SSE 流式聊天 ====================

@router.post("/stream")
async def chat_stream(request: ChatRequest, http_request: Request):
    """SSE 流式聊天端点"""
    from fastapi.responses import StreamingResponse

    session_id = request.session_id or _agent_service.create_session()

    async def event_generator():
        try:
            async for chunk in _agent_service.chat_stream(
                session_id=session_id,
                message=request.message,
                agent_type=request.agent_type,
            ):
                yield f"data: {chunk}\n\n"
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ==================== 非流式聊天 ====================

@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, http_request: Request):
    """非流式聊天端点"""
    session_id = request.session_id or _agent_service.create_session()

    result = await _agent_service.chat(
        session_id=session_id,
        message=request.message,
        agent_type=request.agent_type,
    )
    return ChatResponse(**result)


# ==================== WebSocket 聊天 ====================

@router.websocket("/ws")
async def chat_websocket(websocket: WebSocket):
    """WebSocket 双向聊天"""
    await websocket.accept()

    session_id = _agent_service.create_session()
    await websocket.send_json({
        "type": "system",
        "session_id": session_id,
        "message": "WebSocket 连接已建立",
    })

    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            agent_type = data.get("agent_type", "PM")

            if not message:
                await websocket.send_json({"type": "error", "message": "消息不能为空"})
                continue

            if data.get("stream", True):
                full_reply = ""
                async for chunk in _agent_service.chat_stream(
                    session_id=session_id,
                    message=message,
                    agent_type=agent_type,
                ):
                    full_reply += chunk
                    await websocket.send_json({
                        "type": "chunk",
                        "content": chunk,
                        "done": False,
                    })
                await websocket.send_json({
                    "type": "done",
                    "content": full_reply,
                    "done": True,
                })
            else:
                result = await _agent_service.chat(
                    session_id=session_id,
                    message=message,
                    agent_type=agent_type,
                )
                await websocket.send_json({
                    "type": "reply",
                    **result,
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


# ==================== 会话管理 ====================

@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """获取会话消息历史"""
    messages = _agent_service.get_session_messages(session_id)
    return {"code": 200, "data": {"session_id": session_id, "messages": messages}}


@router.post("/sessions")
async def create_session():
    """创建新会话"""
    session_id = _agent_service.create_session()
    return {"code": 200, "data": {"session_id": session_id}}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""
    success = _agent_service.delete_session(session_id)
    if success:
        return {"code": 200, "message": "会话已删除"}
    return {"code": 404, "message": "会话不存在"}
