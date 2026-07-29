"""FastAPI 应用入口"""
import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import ensure_runtime_schema, init_db

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


async def _embedding_backfill_task():
    """后台任务：周期性扫描 embedding_status='pending' 的知识条目并批量向量化。"""
    while True:
        try:
            await asyncio.sleep(60)
            from app.services.knowledge_service import backfill_pending_embeddings
            processed = await backfill_pending_embeddings()
            if processed:
                logger.info(f"Embedding backfill processed {processed} pending item(s)")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Embedding backfill failed: {e}")
            await asyncio.sleep(300)  # 失败后等 5 分钟重试


async def _usage_flush_task():
    """后台任务：周期性把 LLM 用量缓冲区持久化到 llm_usage_log。"""
    while True:
        try:
            await asyncio.sleep(30)
            from app.core.database import async_session_maker
            from app.ai.model_router import model_router
            async with async_session_maker() as session:
                flushed = await model_router.flush_usage(session)
                if flushed:
                    logger.info(f"LLM usage flushed {flushed} record(s)")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"LLM usage flush failed: {e}")
            await asyncio.sleep(60)


async def _sandbox_reaper_task():
    """后台任务：周期回收空闲超时的沙箱进程（前端 vite 预览 / 后端 java 服务），
    释放进程与端口，防止长跑泄漏（pipeline 未显式 stop 时兜底）。"""
    from app.services.sandbox_preview_service import sandbox_preview_service
    from app.services.backend_runner_service import backend_runner_service
    ttl = settings.pipeline_sandbox_idle_ttl
    while True:
        try:
            await asyncio.sleep(60)
            reaped_fe = await sandbox_preview_service.reap_idle(ttl)
            reaped_be = await backend_runner_service.reap_idle(ttl)
            if reaped_fe or reaped_be:
                logger.info(f"Sandbox reaper: stopped {reaped_fe} frontend + {reaped_be} backend idle process(es)")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Sandbox reaper failed: {e}")
            await asyncio.sleep(120)


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

    await ensure_runtime_schema()
    try:
        from app.ai.flow_manager import recover_stale_running_pipelines
        recovered = await recover_stale_running_pipelines()
        if recovered:
            logger.warning(f"Recovered {recovered} stale running pipeline(s) after startup")
    except Exception as e:
        logger.warning(f"Failed to recover stale running pipelines: {e}")

    # 启动每日 AI 升级定时任务
    upgrade_task = asyncio.create_task(_daily_ai_upgrade_task())
    logger.info("✅ 每日 AI 升级定时任务已启动 (每天 02:05)")

    # 启动知识库 embedding 回填任务（每 60s 扫一次 pending 队列）
    embedding_task = asyncio.create_task(_embedding_backfill_task())
    logger.info("✅ 知识库 embedding 回填任务已启动 (每 60s)")

    # 启动 LLM 用量持久化任务（每 30s 把缓冲区写入 llm_usage_log）
    usage_task = asyncio.create_task(_usage_flush_task())
    logger.info("✅ LLM 用量持久化任务已启动 (每 30s)")

    # 启动沙箱回收任务（每 60s，空闲超 ttl 自动 stop 释放进程/端口）
    reaper_task = asyncio.create_task(_sandbox_reaper_task())
    logger.info(f"✅ 沙箱回收任务已启动 (每 60s，空闲 {settings.pipeline_sandbox_idle_ttl}s 自动 stop)")

    yield

    # 关闭时
    upgrade_task.cancel()
    embedding_task.cancel()
    usage_task.cancel()
    reaper_task.cancel()
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
    # Expose interactive API docs only in debug mode; hide schema in production.
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
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
