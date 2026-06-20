import os
os.environ["APP_DATABASE_URL"] = "sqlite+aiosqlite:///./test_agent.db"

import pytest_asyncio
from agent.db import Base, engine
from agent.config import get_settings

get_settings.cache_clear()


@pytest_asyncio.fixture(autouse=True)
async def _fresh_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
