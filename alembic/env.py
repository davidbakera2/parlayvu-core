from logging.config import fileConfig
import os

from dotenv import load_dotenv
from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Load environment exactly like the main app (supports .env for DATABASE_URL)
load_dotenv(override=True)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ParlayVU: Use our SQLAlchemy 2.0 models for autogenerate support.
# This pulls in all tables (Client, Project, ConversationTurn, AgentEvent, etc.)
from app.models import Base
target_metadata = Base.metadata

# Allow DATABASE_URL from environment to override alembic.ini (matches app/database.py behavior)
if os.getenv("DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL"))

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    For `alembic revision --autogenerate` we only need the metadata (no live DB).
    We therefore only create a real connection when actually executing migrations.
    """
    url = config.get_main_option("sqlalchemy.url") or ""

    # For `alembic revision --autogenerate` (and other metadata-only operations)
    # we do not need a live database connection. Skip engine creation entirely
    # if the URL is missing or still the default placeholder from alembic init.
    if context.is_offline_mode() or not url or "driver://user:pass" in url:
        # Autogenerate / revision without a live DB connection.
        # Supplying dialect_name allows Alembic to compare models vs. the target dialect.
        context.configure(
            target_metadata=target_metadata,
            dialect_name="postgresql",   # ParlayVU uses Neon Postgres + psycopg2
        )
        # Do not start a transaction here — revision --autogenerate only needs the configured context.
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
