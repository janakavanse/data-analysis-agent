import pathlib
import pytest

pytest.importorskip("playwright")
from playwright.sync_api import expect


def test_user_gets_an_answer(page):
    """Full browser journey: paste CSV data → ask question → answer contains a column name."""
    page.goto("http://localhost:8001")

    # DATA-INGEST: fill the CSV textarea with the fixture (required for C-SESSION-SCOPE)
    fixture = pathlib.Path("scripts/fixtures/sample_data.csv").read_text()
    page.get_by_role("textbox", name="data").fill(fixture)

    page.get_by_role("textbox", name="goal").fill("What is the mean value of each numeric column?")
    page.get_by_role("button", name="Run").click()

    answer = page.get_by_test_id("answer")
    expect(answer).not_to_be_empty(timeout=60_000)
    # Assert a real column name from the fixture appears — not just non-empty (a "no data loaded"
    # error is also non-empty, which would false-green a wrong-answer journey)
    expect(answer).to_contain_text("salary")
    expect(page.get_by_role("link", name="trace")).to_be_visible()
