import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection

# Add the app directory to the path
sys.path.append(str(Path(__file__).resolve().parents[1]))

# Load environment variables from .env if it exists
from dotenv import load_dotenv
load_dotenv()

from app.core.config import settings
from app.db.base import Base
from app.models import *  # noqa: F403,F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Convert async postgres URL to sync for alembic
database_url = os.getenv("DATABASE_URL", str(settings.DATABASE_URL))
# Replace asyncpg driver with psycopg2 for synchronous migrations
sync_database_url = database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
sync_database_url = sync_database_url.replace("?sslmode=require", "")
sync_database_url = sync_database_url.replace("?sslmode=disable", "")
config.set_main_option("sqlalchemy.url", sync_database_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()