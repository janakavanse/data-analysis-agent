import pytest


@pytest.fixture(autouse=True)
def _fresh_db():
    # e2e tests hit the live server's DB — no table reset needed here.
    # This no-op overrides the async _fresh_db from tests/conftest.py to avoid
    # the event-loop conflict between pytest-asyncio and Playwright's sync API.
    yield
