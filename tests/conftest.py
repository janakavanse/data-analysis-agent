import os

# Must be set before agent.db is imported (engine is built at import time)
os.environ["APP_DATABASE_URL"] = "sqlite+aiosqlite:///./test_agent.db"
os.environ["APP_LLM_API_KEY"] = "fake-key-for-tests"

import pytest_asyncio
from agent.db import Base, engine


@pytest_asyncio.fixture(autouse=True)
async def _fresh_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
