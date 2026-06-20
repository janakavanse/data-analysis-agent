import agent.eval_lint


def test_eval_lint():
    assert agent.eval_lint.main() == 0
