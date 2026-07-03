"""Unit tests for the structured generate_code response parser — no LLM call,
pure text-parsing logic."""
import pytest

from analysis.codegen import CodegenResponseError, parse_codegen_response


def test_parses_ok_status_with_bare_json():
    text = (
        '{"status": "ok", "code": "answer = \\"42\\"", '
        '"followups": ["a?", "b?"], "message": null}'
    )
    decision = parse_codegen_response(text)
    assert decision.status == "ok"
    assert decision.code == 'answer = "42"'
    assert decision.followups == ["a?", "b?"]
    assert decision.message is None


def test_parses_ok_status_wrapped_in_json_fence():
    text = (
        "Here you go:\n```json\n"
        '{"status": "ok", "code": "answer = \'x\'", "followups": [], "message": null}'
        "\n```"
    )
    decision = parse_codegen_response(text)
    assert decision.status == "ok"
    assert decision.code == "answer = 'x'"


def test_parses_needs_clarification_status():
    text = '{"status": "needs_clarification", "code": null, "followups": [], "message": "Which column do you mean by \'that column\'?"}'
    decision = parse_codegen_response(text)
    assert decision.status == "needs_clarification"
    assert decision.code is None
    assert decision.message


def test_parses_unanswerable_status():
    text = '{"status": "unanswerable", "code": null, "followups": [], "message": "Column \'revenu\' does not exist."}'
    decision = parse_codegen_response(text)
    assert decision.status == "unanswerable"
    assert decision.code is None
    assert "revenu" in decision.message


def test_caps_followups_to_three():
    text = (
        '{"status": "ok", "code": "answer = \'x\'", '
        '"followups": ["a", "b", "c", "d", "e"], "message": null}'
    )
    decision = parse_codegen_response(text)
    assert len(decision.followups) == 3


def test_unparseable_json_raises_codegen_response_error():
    with pytest.raises(CodegenResponseError):
        parse_codegen_response("not json at all")


def test_ok_status_without_code_raises():
    with pytest.raises(CodegenResponseError):
        parse_codegen_response('{"status": "ok", "code": null, "followups": [], "message": null}')


def test_clarification_status_without_message_raises():
    with pytest.raises(CodegenResponseError):
        parse_codegen_response(
            '{"status": "needs_clarification", "code": null, "followups": [], "message": null}'
        )


def test_invalid_status_value_raises():
    with pytest.raises(CodegenResponseError):
        parse_codegen_response('{"status": "bogus", "code": null, "followups": [], "message": "x"}')
