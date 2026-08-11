from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.security import RequestContext, require_request_context


engine = create_async_engine(settings.database_url, pool_pre_ping=True)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def tenant_session(
    context: RequestContext = Depends(require_request_context),
) -> AsyncIterator[AsyncSession]:
    """Open a transaction with PostgreSQL RLS bound to the authenticated tenant."""
    async with session_factory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(context.tenant_id)},
        )
        session.info["request_context"] = context
        yield session
