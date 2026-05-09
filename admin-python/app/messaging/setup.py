"""适配器自动注册

在应用启动时自动注册所有可用的渠道适配器。
"""
import logging
from typing import Optional

from app.core.config import settings
from app.messaging.adapter.base import adapter_registry
from app.messaging.adapter.telegram.adapter import TelegramAdapter
from app.messaging.adapter.discord.adapter import DiscordAdapter
from app.messaging.adapter.slack.adapter import SlackAdapter
from app.messaging.adapter.feishu.adapter import FeishuAdapter
from app.messaging.schemas import ChannelType, ChannelConfig
from app.messaging.service.message_router import get_message_router

logger = logging.getLogger(__name__)


def register_all_adapters() -> None:
    """注册所有适配器类到全局注册表"""
    adapter_registry.register(TelegramAdapter)
    adapter_registry.register(DiscordAdapter)
    adapter_registry.register(SlackAdapter)
    adapter_registry.register(FeishuAdapter)
    logger.info("[Messaging] 已注册所有渠道适配器")


async def initialize_configured_adapters() -> dict[ChannelType, bool]:
    """初始化已配置的渠道适配器

    根据环境变量配置，自动初始化已配置凭证的适配器。

    Returns:
        各渠道初始化结果
    """
    register_all_adapters()
    router = get_message_router()
    results = {}

    # Telegram
    if settings.telegram_bot_token:
        config = ChannelConfig(
            channel_type=ChannelType.TELEGRAM,
            extra={
                "bot_token": settings.telegram_bot_token,
                "secret_token": settings.telegram_secret_token,
            }
        )
        router.register_adapter(config)
        results[ChannelType.TELEGRAM] = await router.initialize_adapter(ChannelType.TELEGRAM)

    # Discord
    if settings.discord_bot_token:
        config = ChannelConfig(
            channel_type=ChannelType.DISCORD,
            extra={
                "bot_token": settings.discord_bot_token,
                "application_id": settings.discord_application_id,
                "public_key": settings.discord_public_key,
            }
        )
        router.register_adapter(config)
        results[ChannelType.DISCORD] = await router.initialize_adapter(ChannelType.DISCORD)

    # Slack
    if settings.slack_bot_token:
        config = ChannelConfig(
            channel_type=ChannelType.SLACK,
            extra={
                "bot_token": settings.slack_bot_token,
                "app_token": settings.slack_app_token,
                "signing_secret": settings.slack_signing_secret,
            }
        )
        router.register_adapter(config)
        results[ChannelType.SLACK] = await router.initialize_adapter(ChannelType.SLACK)

    # Feishu
    if settings.feishu_app_id:
        config = ChannelConfig(
            channel_type=ChannelType.FEISHU,
            extra={
                "app_id": settings.feishu_app_id,
                "app_secret": settings.feishu_app_secret,
                "encrypt_key": settings.feishu_encrypt_key,
                "verification_token": settings.feishu_verification_token,
            }
        )
        router.register_adapter(config)
        results[ChannelType.FEISHU] = await router.initialize_adapter(ChannelType.FEISHU)

    # 记录初始化结果
    for channel_type, success in results.items():
        if success:
            logger.info(f"[Messaging] {channel_type.value} 初始化成功")
        else:
            logger.warning(f"[Messaging] {channel_type.value} 初始化失败")

    return results


async def setup_messaging() -> None:
    """完整的消息模块初始化

    包括：
    1. 初始化路由器
    2. 注册适配器
    3. 初始化已配置的渠道
    """
    from app.messaging.service.message_router import init_message_router

    # 初始化路由器
    router = await init_message_router()

    # 初始化已配置的适配器
    await initialize_configured_adapters()

    logger.info("[Messaging] 消息模块初始化完成")


async def shutdown_messaging() -> None:
    """关闭消息模块"""
    from app.messaging.service.message_router import get_message_router

    router = get_message_router()
    await router.shutdown()
    logger.info("[Messaging] 消息模块已关闭")
