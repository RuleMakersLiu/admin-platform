"""FastAPI 应用入口"""
import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import init_db

# 配置日志
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ==================== 每日 AI 升级定时任务 ====================

async def _daily_ai_upgrade_task():
    """后台定时任务：每天凌晨 2 点执行 AI 升级分析"""
    while True:
        try:
            # 等到凌晨 2 点
            now = asyncio.get_event_loop().time()
            import datetime
            dt = datetime.datetime.now()
            target = dt.replace(hour=2, minute=5, second=0, microsecond=0)
            if dt >= target:
                target = target.replace(day=target.day + 1)
            delay = (target - dt).total_seconds()
            logger.info(f"Next AI upgrade scheduled in {delay:.0f}s")
            await asyncio.sleep(delay)

            # 执行升级分析
            from app.services.ai_upgrade_service import ai_upgrade_service
            result = await ai_upgrade_service.run_daily_upgrade()
            logger.info(f"Daily AI upgrade completed: {result.get('knowledge_id', 'N/A')}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Daily AI upgrade failed: {e}")
            await asyncio.sleep(3600)  # 失败后等 1 小时重试


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info(f"🚀 {settings.app_name} v{settings.app_version} 启动中...")

    # 初始化消息模块
    try:
        from app.messaging.setup import setup_messaging, shutdown_messaging
        await setup_messaging()
        logger.info("✅ 消息模块初始化完成")
    except Exception as e:
        logger.warning(f"⚠️ 消息模块初始化失败: {e}")

    # await init_db()  # 生产环境建议使用Alembic迁移

    # 启动每日 AI 升级定时任务
    upgrade_task = asyncio.create_task(_daily_ai_upgrade_task())
    logger.info("✅ 每日 AI 升级定时任务已启动 (每天 02:05)")

    yield

    # 关闭时
    upgrade_task.cancel()
    try:
        from app.messaging.setup import shutdown_messaging
        await shutdown_messaging()
    except Exception:
        pass
    logger.info(f"👋 {settings.app_name} 关闭中...")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Admin Platform Python Backend with AI Agents",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册API路由
app.include_router(api_router, prefix="/api")


# 健康检查
@app.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "ok",
        "service": "admin-python",
        "version": settings.app_version,
    }


# 根路径
@app.get("/")
async def root():
    """根路径"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
