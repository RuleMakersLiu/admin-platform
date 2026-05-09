"""多渠道消息 API 路由"""
import hashlib
import hmac
import logging
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer

from app.api.v1.auth import get_current_user
from app.messaging.schemas import (
    ChannelType,
    SendMessageRequest,
    WebhookPayload,
    Response,
)
from app.messaging.service.message_router import get_message_router

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/messaging", tags=["多渠道消息"])
security = HTTPBearer()


# ==================== Webhook 签名验证 ====================

def _verify_discord_signature(body: bytes, signature: str, timestamp: str,
                               public_key: str = "") -> bool:
    """验证 Discord webhook 签名 (Ed25519)"""
    if not signature or not public_key:
        logger.warning("Discord webhook: 签名或公钥未配置，跳过验证")
        return True
    try:
        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignatureError
        verify_key = VerifyKey(bytes.fromhex(public_key))
        message = timestamp.encode() + body
        verify_key.verify(message, bytes.fromhex(signature))
        return True
    except (ImportError, BadSignatureError, Exception) as e:
        logger.warning(f"Discord 签名验证失败: {e}")
        return False


def _verify_telegram_signature(body: bytes, signature: str,
                                bot_token: str = "") -> bool:
    """验证 Telegram webhook 签名 (HMAC-SHA256)"""
    if not signature or not bot_token:
        logger.warning("Telegram webhook: 签名或 token 未配置，跳过验证")
        return True
    expected = hmac.new(
        bot_token.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _verify_webhook_signature(channel_type: ChannelType, request: Request,
                               body: bytes) -> bool:
    """根据渠道类型验证 webhook 签名"""
    signature = request.headers.get("X-Signature-Ed25519", "")
    signature_sha256 = request.headers.get("X-Signature-SHA256", "")

    if channel_type == ChannelType.DISCORD:
        timestamp = request.headers.get("X-Signature-Timestamp", "")
        return _verify_discord_signature(body, signature, timestamp)
    elif channel_type == ChannelType.TELEGRAM:
        return _verify_telegram_signature(body, signature_sha256)
    # Slack 等其他渠道暂不验证
    return True


# ==================== 消息发送 ====================

@router.post("/send", response_model=Response)
async def send_message(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """发送消息到指定渠道"""
    try:
        body = await request.json()
        channel = body.get("channel", "")
        channel_id = body.get("channel_id", "")
        content = body.get("content", "")

        try:
            channel_type = ChannelType(channel)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"不支持的渠道: {channel}")

        message_router = get_message_router()
        msg_request = SendMessageRequest(
            channel_type=channel_type,
            channel_id=channel_id,
            content=content,
            sender_id=str(user.get("id", "")),
            message_type=body.get("message_type"),
            metadata=body.get("metadata"),
            reply_to=body.get("reply_to"),
            attachments=body.get("attachments"),
        )

        result = await message_router.send_message(msg_request)

        return Response(
            success=result.success,
            data=result,
            message="发送成功" if result.success else result.error,
        )
    except HTTPException:
        raise
    except Exception as e:
        return Response(success=False, message=str(e))


# ==================== 渠道管理 ====================

@router.get("/channels", response_model=Response)
async def list_channels(
    user: dict = Depends(get_current_user),
):
    """获取所有启用的渠道"""
    try:
        message_router = get_message_router()
        channels = []

        for channel_type in ChannelType:
            if channel_type == ChannelType.WEBSOCKET:
                continue

            adapter = message_router._adapters.get(channel_type)
            channels.append({
                "id": channel_type.value,
                "type": channel_type.value,
                "name": channel_type.value.title(),
                "enabled": adapter is not None and getattr(adapter, "is_initialized", False),
            })

        return Response(success=True, data=channels, message="获取成功")
    except Exception:
        return Response(success=True, data=[], message="获取成功")


# ==================== Discord 特殊回调（必须放在通用路由之前） ====================

@router.post("/webhook/discord")
async def handle_discord_webhook(request: Request):
    """Discord Interactions Webhook"""
    try:
        body_bytes = await request.body()
        body = __import__("json").loads(body_bytes)

        # Discord PING 响应
        if body.get("type") == 1:
            return {"type": 1}

        # 验证签名
        if not _verify_webhook_signature(ChannelType.DISCORD, request, body_bytes):
            raise HTTPException(status_code=401, detail="签名验证失败")

        payload = WebhookPayload(
            channel_type=ChannelType.DISCORD,
            raw_data=body,
            signature=request.headers.get("X-Signature-Ed25519"),
            timestamp=int(time.time() * 1000),
        )

        message_router = get_message_router()
        result = await message_router.handle_webhook(ChannelType.DISCORD, payload)

        return {"success": True, "data": result.model_dump() if result else None}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Discord webhook 处理失败: {e}")
        return {"success": False, "error": str(e)}


# ==================== Webhook 回调 ====================

@router.post("/webhook/{adapter_name}")
async def handle_webhook(adapter_name: str, request: Request):
    """处理各渠道的 Webhook 回调"""
    try:
        try:
            channel_type = ChannelType(adapter_name)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"不支持的渠道: {adapter_name}")

        body_bytes = await request.body()
        body = __import__("json").loads(body_bytes)

        # 验证签名
        if not _verify_webhook_signature(channel_type, request, body_bytes):
            raise HTTPException(status_code=401, detail="签名验证失败")

        payload = WebhookPayload(
            channel_type=channel_type,
            raw_data=body,
            signature=request.headers.get("X-Signature-Ed25519")
            or request.headers.get("X-Signature-SHA256"),
            timestamp=int(time.time() * 1000),
        )

        message_router = get_message_router()
        result = await message_router.handle_webhook(channel_type, payload)

        return {"success": True, "data": result.model_dump() if result else None}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook 处理失败 ({adapter_name}): {e}")
        return {"success": False, "error": str(e)}
