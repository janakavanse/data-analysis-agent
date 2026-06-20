import pathlib
import pytest

pytest.importorskip("playwright")
from playwright.sync_api import expect


def test_user_gets_an_answer(page):
    """Full browser journey: paste a document → ask a question → grounded answer contains the fact."""
    page.goto("http://localhost:8001")

    fixture = pathlib.Path("scripts/fixtures/handbook.txt").read_text()
    page.get_by_role("textbox", name="data").fill(fixture)

    page.get_by_role("textbox", name="goal").fill("How many paid vacation days do full-time employees get per year?")
    page.get_by_role("button", name="Run").click()

    answer = page.get_by_test_id("answer")
    expect(answer).not_to_be_empty(timeout=60_000)
    # A real grounded fact from the handbook — not just non-empty
    expect(answer).to_contain_text("20")
    expect(page.get_by_role("link", name="trace")).to_be_visible()
