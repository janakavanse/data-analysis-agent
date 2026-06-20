import os
from types import SimpleNamespace

import pytest

from agent import ask, calculator


# --- tool tests: deterministic, no API key needed ---
def test_calculator_basic():
    assert calculator("17 * 23 + 5") == "396"
    assert calculator("2 ** 10") == "1024"
    assert calculator("(3 + 4) * 2") == "14"


def test_calculator_rejects_unsafe():
    # names / calls / attribute access must never reach eval (action-safety)
    with pytest.raises(ValueError):
        calculator("__import__('os').system('echo hi')")
    with pytest.raises(ValueError):
        calculator("x + 1")


# --- acceptance: the real agent must answer 17*23+5 with 396 (real Gemini call) ---
@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="real run needs GEMINI_API_KEY")
def test_acceptance_real_gemini():
    answer = ask("what is 17 * 23 plus 5?")
    assert "396" in answer, f"expected 396 in answer, got: {answer!r}"


# --- loop mechanics: keyless, via an injected fake client (the FakeModel-style loop test) ---
def _resp(parts, text=None):
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=parts))], text=text)


def _call(name, args):
    return SimpleNamespace(function_call=SimpleNamespace(name=name, args=args))


class _FakeClient:
    """Scripts client.models.generate_content; repeats the last response once exhausted."""

    def __init__(self, scripted):
        self.models = SimpleNamespace(generate_content=self._gen)
        self._scripted, self._i = scripted, 0

    def _gen(self, *, model, contents, config):
        r = self._scripted[min(self._i, len(self._scripted) - 1)]
        self._i += 1
        return r


def test_loop_recovers_from_tool_error():
    # model divides by zero, sees the error fed back, then answers — the loop must not crash
    fake = _FakeClient([
        _resp([_call("calculator", {"expression": "1/0"})]),
        _resp([], text="I couldn't compute that."),
    ])
    assert "couldn't" in ask("divide 1 by 0", client=fake).lower()


def test_loop_exhausts_max_steps():
    # a model that always calls the tool must terminate at max_steps, not loop forever
    fake = _FakeClient([_resp([_call("calculator", {"expression": "1+1"})])])
    assert ask("loop", client=fake, max_steps=3) == "(ran out of steps)"
