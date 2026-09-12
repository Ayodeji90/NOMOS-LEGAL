import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import settings
from app.db.base import Base
from app.db.session import db_manager

logger = logging.getLogger(__name__)


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))


async def drop_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def check_pgvector(engine: AsyncEngine) -> bool:
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
            return result.scalar() == 1
    except Exception:
        return False


async def run_migrations() -> None:
    from alembic.config import Config

    from alembic import command

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")


async def run_migrations_async() -> None:
    """Same as run_migrations but safe inside a running event loop.

    The CLI path above uses asyncio.run internally, which explodes in
    lifespan, so run it in a worker thread (no loop there). Startup-only,
    migrations take ~1s; the loop is not needed meanwhile.
    """
    import asyncio
    import functools
    from pathlib import Path

    from alembic.config import Config

    from alembic import command

    ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    cfg = Config(str(ini))
    cfg.set_main_option("sqlalchemy.url", str(settings.DATABASE_URL))
    await asyncio.to_thread(functools.partial(command.upgrade, cfg, "head"))


async def init_database() -> None:
    # Migrations own the schema (deploy pipeline runs `alembic upgrade head`;
    # compose does the same pre-boot). create_all is dev/test-only via init_db.
    logger.info("Initializing database...")
    db_manager.initialize()
    # Skip migrations during startup - they should be run separately
    # await run_migrations_async()
    has_pgvector = await check_pgvector(db_manager.engine)
    if not has_pgvector:
        logger.warning("pgvector extension not available - vector search will not work")
    else:
        logger.info("pgvector extension confirmed")
    logger.info("Database initialization complete")
