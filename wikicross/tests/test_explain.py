from fastapi.testclient import TestClient

from wikicross import app as m


def test_explain_keeps_only_phrases_in_the_quote_and_skips_missing_translations(monkeypatch):
    answer = {
        "discrepancy": True,
        "title": "Finnish calls it a war, Russian a conflict",
        "description": "Finnish says <mark>war</mark>, Russian <mark>conflict</mark>.",
        "quotes": {
            "fi": {"english": "It was a <mark>war</mark>.", "heading": "History", "phrases": ["sota", "not in the quote"]},
            "ru": {"english": "  ", "heading": "", "phrases": ["конфликт"]},  # no usable translation
        },
    }
    monkeypatch.setattr(m, "chat", lambda system, user, schema: answer)
    passages = [
        {"lang": "fi", "heading": "Historia", "text": "Se oli sota. Muuta.", "sentence": "Se oli sota."},
        {"lang": "ru", "heading": "История", "text": "Это был конфликт.", "sentence": "Это был конфликт."},
        {"lang": "sv", "heading": "", "text": "Det var ett krig.", "sentence": "Det var ett krig."},  # left out by the LLM
    ]
    r = TestClient(m.app, client=("127.0.0.1", 1)).post("/api/explain", json={"passages": passages})
    assert r.status_code == 200
    x = r.json()
    assert x["title"] == answer["title"] and x["description"] == answer["description"] and x["discrepancy"] is True
    assert x["quotes"] == {"fi": {"english": "It was a <mark>war</mark>.", "heading": "History", "phrases": ["sota"]}}
