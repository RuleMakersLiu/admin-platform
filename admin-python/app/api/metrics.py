"""生产监控端点：/metrics（Prometheus 格式）+ /health/detail（详细健康）。

/metrics：流水线计数、活跃沙箱、LLM 用量汇总、DB 连接池状态。
/health/detail：服务依赖（postgres/redis/glm api）连通性 + 版本信息。
"""
import time
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, text

from app.core.database import engine, async_session_maker
from app.core.config import settings
from app.core.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/metrics", tags=["监控"], dependencies=[Depends(get_current_user)])


@router.get("")
async def prometheus_metrics():
    """Prometheus 格式指标（text/plain）。"""
    lines = []

    # Pipeline 计数
    try:
        async with async_session_maker() as session:
            for status_val in ("pending", "running", "completed", "failed", "needs_human"):
                count = (await session.execute(
                    text(f"SELECT COUNT(*) FROM dev_pipeline WHERE status='{status_val}' AND is_deleted=0")
                )).scalar()
                lines.append(f'pipeline_count{{status="{status_val}"}} {count}')

            # 今日完成数
            today_start = int((time.time() - 86400) * 1000)
            today = (await session.execute(
                text(f"SELECT COUNT(*) FROM dev_pipeline WHERE status='completed' AND update_time>{today_start} AND is_deleted=0")
            )).scalar()
            lines.append(f'pipeline_completed_today {today}')

            # eval 平均分
            avg = (await session.execute(
                text("SELECT COALESCE(AVG(overall_score),0) FROM pipeline_eval_result WHERE is_deleted=0")
            )).scalar()
            lines.append(f'pipeline_eval_avg_score {avg}')

            # 活跃沙箱进程数
            from app.services.sandbox_preview_service import sandbox_preview_service
            from app.services.backend_runner_service import backend_runner_service
            lines.append(f'sandbox_preview_active {len(sandbox_preview_service._processes)}')
            lines.append(f'sandbox_backend_active {len(backend_runner_service._processes)}')
    except Exception as e:
        lines.append(f'# DB query error: {e}')

    # DB 连接池
    try:
        pool = engine.pool
        lines.append(f'db_pool_size {pool.size()}')
        lines.append(f'db_pool_checked_in {pool.checkedin()}')
        lines.append(f'db_pool_checked_out {pool.checkedout()}')
        lines.append(f'db_pool_overflow {pool.overflow()}')
    except Exception:
        pass

    # 应用信息
    lines.append(f'app_info{{version="{settings.app_version}",debug="{str(settings.debug).lower()}"}} 1')

    return "\n".join(lines) + "\n"


@router.get("/health-detail")
async def health_detail():
    """详细健康检查（服务依赖连通性）。"""
    checks = {}

    # Postgres
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = {"status": "ok"}
    except Exception as e:
        checks["postgres"] = {"status": "error", "detail": str(e)[:200]}

    # Redis
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        await r.ping()
        await r.aclose()
        checks["redis"] = {"status": "ok"}
    except Exception as e:
        checks["redis"] = {"status": "error", "detail": str(e)[:200]}

    # GLM API（只检查 key 是否配置，不实际调用）
    checks["glm_api"] = {"status": "ok" if settings.zai_api_key else "error", "model": settings.zai_default_model}

    # DB 连接池
    try:
        pool = engine.pool
        checks["db_pool"] = {
            "size": pool.size(), "checked_out": pool.checkedout(),
            "checked_in": pool.checkedin(), "overflow": pool.overflow(),
        }
    except Exception:
        pass

    # 沙箱执行模式
    checks["sandbox"] = {"mode": settings.sandbox_execution_mode}

    all_ok = all(v.get("status") != "error" for v in checks.values() if isinstance(v, dict) and "status" in v)

    return {
        "code": 200,
        "data": {
            "healthy": all_ok,
            "version": settings.app_version,
            "debug": settings.debug,
            "uptime_checks": checks,
        },
    }
