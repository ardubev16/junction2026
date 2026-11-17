from fastapi import HTTPException
from fastapi.testclient import TestClient

from wikicross import app as m


def test_explain_keeps_only_phrases_in_the_quote_and_skips_missing_translations(monkeypatch):
    answer = {
        "discrepancy": True,
        "kind": "bias",
        "title": "Finnish calls it a war, Russian a conflict",
        "description": "Finnish says <mark>war</mark>, Russian <mark>conflict</mark>.",
        "quotes": {
            "fi": {
                "english": "It was a <mark>war</mark>.",
                "heading": "History",
                "phrases": ["sota", "not in the quote"],
            },
            "ru": {"english": "  ", "heading": "", "phrases": ["конфликт"]},  # no usable translation
        },
    }
    monkeypatch.setattr(m, "chat", lambda *_: answer)
    passages = [
        {"lang": "fi", "heading": "Historia", "text": "Se oli sota. Muuta.", "sentence": "Se oli sota."},
        {"lang": "ru", "heading": "История", "text": "Это был конфликт.", "sentence": "Это был конфликт."},
        {"lang": "sv", "heading": "", "text": "Det var ett krig.", "sentence": "Det var ett krig."},  # left out
    ]
    x = m.explain(passages)
    assert x["title"] == answer["title"]
    assert x["description"] == answer["description"]
    assert x["discrepancy"] is True
    assert x["quotes"] == {"fi": {"english": "It was a <mark>war</mark>.", "heading": "History", "phrases": ["sota"]}}
    assert x["kind"] == "bias"
    answer["kind"] = "contradiction"  # not one of KINDS: no badge rather than an unknown one
    assert m.explain(passages)["kind"] is None


def test_a_failed_llm_call_leaves_the_finding_usable(monkeypatch):
    def fail(*_):
        raise HTTPException(502, "LLM error 503: overloaded")

    monkeypatch.setattr(m, "chat", fail)
    member = {"lang": "fi", "heading": "", "text": "Se oli sota.", "sentence": "Se oli sota."}
    findings = [{"members": [member, {**member, "lang": "sv"}]}]
    steps = []
    m.explain_page(findings, lambda key, detail="": steps.append((key, detail)))
    assert findings[0]["ai"] == {"error": "LLM error 503: overloaded"}
    assert steps[-1] == ("ai", "1 of 1, 1 failed")


def test_ai_endpoints_take_only_quotes_by_place(monkeypatch):
    def fail(*_):
        raise AssertionError("LLM called")

    monkeypatch.setattr(m, "chat", fail)
    client = TestClient(m.app, client=("127.0.0.1", 1))
    quote = {"lang": "fi", "page_id": 1, "seq": 0, "n": 0}
    assert client.post("/api/translate", json={"quotes": [quote] * 201}).status_code == 422
    assert client.post("/api/translate", json={"quotes": [{"lang": "fi", "text": "x"}]}).status_code == 422
    assert client.post("/api/explain", json={"quotes": [quote] * 4}).status_code == 422  # a card explains 3
    assert client.post("/api/explain", json={"quotes": [quote]}).status_code == 422
