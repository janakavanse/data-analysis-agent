"""Reconciliation gate: the spec and code must reconcile (every criterion bound, every target real)."""
import agent.analyze


def test_spec_and_code_reconcile():
    assert agent.analyze.main() == 0
