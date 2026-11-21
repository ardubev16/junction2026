import pytest
from fastapi.testclient import TestClient

from wikicross import app as m


def test_explain_keeps_only_phrases_in_the_quote_and_skips_missing_translations(monkeypatch):
    answer = {
        "subject": "what the conflict was",
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
    assert x["quotes"] == {"fi": {"english": "It was a <mark>war</mark>.", "heading": "History", "phrases": ["sota"]}}
    assert x["kind"] == "bias"
    answer["kind"] = "contradiction"  # not one of KINDS: no badge rather than an unknown one
    assert m.explain(passages)["kind"] is None


@pytest.mark.parametrize(
    ("phrase", "sentence", "found"),
    [
        ("122,590", "Dân số của Kuopio là 122.590 người", "122.590"),  # digit grouping differs
        ("121,557", "Kuopio hevur 121 557 íbúgvar", "121 557"),
        ("19156", "adunay 19,156 nga empleyado", "19,156"),
        ("Most Popular", "the most popular one", "most popular"),  # case
        ("na  serbisyo", "pinakasikat na serbisyo sa", "na serbisyo"),  # spacing
        ("most popular service", "ang pinakasikat na serbisyo", None),  # given in English
        ("a.b (c)", "x a.b (c) y", "a.b (c)"),  # regex characters
        ("  ", "x", None),
    ],
)
def test_locate_finds_a_phrase_as_the_quote_writes_it(phrase, sentence, found):
    assert m.locate(phrase, sentence) == found


def test_a_discrepancy_needs_a_shared_subject_visible_in_the_quotes(monkeypatch):
    fi = {"lang": "fi", "heading": "", "text": "Vuonna 1918. Asukkaita 900.", "sentence": "Vuonna 1918."}
    sv = {"lang": "sv", "heading": "", "text": "År 1920. Invånare 800.", "sentence": "År 1920."}

    def verdict(subject, fi_phrase, sv_phrase):
        answer = {
            "subject": subject,
            "discrepancy": True,
            "kind": "factual",
            "title": "t",
            "description": "d",
            "quotes": {
                "fi": {"english": "In <mark>1918</mark>.", "heading": "", "phrases": [fi_phrase]},
                "sv": {"english": "In <mark>1920</mark>.", "heading": "", "phrases": [sv_phrase]},
            },
        }
        monkeypatch.setattr(m, "chat", lambda *_: answer)
        return m.explain([fi, sv])["discrepancy"]

    assert verdict("the year", "1918", "1920") is True
    assert verdict("", "1918", "1920") is False  # no shared subject
    assert verdict("the population", "900", "800") is False  # figures found only in the passages


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
