import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure the src/ directory is on the path so imports work when alembic runs
# from the repo root (where alembic.ini lives).
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / "src"))

# Alembic Config object — gives access to the alembic.ini values
config = context.config

# Interpret the alembic.ini logging configuration
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import models so autogenerate can detect them
from data_analyst.db.models import Base  # noqa: E402

target_metadata = Base.metadata


def _get_url() -> str:
    # Resolve DATABASE_URL: first try env var (with and without DA_ prefix),
    # then fall back to pydantic-settings.
    url = (
        os.environ.get("DA_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
    )
    if url:
        return url
    # Fall through to pydantic-settings (reads .env)
    from data_analyst.config.settings import get_settings
    return get_settings().database_url


def _make_url_absolute(url: str) -> str:
    """Convert a relative sqlite:/// URL to absolute so alembic finds the file."""
    prefix = "sqlite:///"
    if url.startswith(prefix):
        path = url[len(prefix):]
        if path and not os.path.isabs(path):
            abs_path = str(repo_root / path)
            return f"{prefix}{abs_path}"
    return url


def run_migrations_offline() -> None:
    url = _make_url_absolute(_get_url())
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _make_url_absolute(_get_url())
    # Ensure the parent directory exists for SQLite
    if url.startswith("sqlite:///"):
        db_path = url[len("sqlite:///"):]
        if db_path:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
