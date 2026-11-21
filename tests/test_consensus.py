from wikicross import app as m

QUOTES = [{"lang": "fi", "sentence": "Asukkaita 120 000."}, {"lang": "ceb", "sentence": "109,455 ka molupyo."}]
OTHERS = [{"lang": "sv", "sentence": "120 000 invånare."}, {"lang": "de", "sentence": "Eine Stadt."}]


def test_positions_keep_each_known_edition_once_most_editions_first(monkeypatch):
    answer = {
        "positions": [
            {"claim": "109,455", "editions": ["ceb", "xx"]},  # xx: not an edition asked about
            {"claim": "120,000", "editions": ["fi", "sv", "ceb"]},  # ceb again: already placed
            {"claim": "nothing", "editions": ["xx"]},
            "junk",
        ]
    }
    monkeypatch.setattr(m, "chat", lambda *_: answer)
    assert m.consensus("population", QUOTES, OTHERS) == [
        {"claim": "120,000", "editions": ["fi", "sv"]},
        {"claim": "109,455", "editions": ["ceb"]},
    ]


def test_no_other_edition_asks_nothing(monkeypatch):
    def fail(*_):
        raise AssertionError("no LLM call without other editions")

    monkeypatch.setattr(m, "chat", fail)
    assert m.consensus("population", QUOTES, []) == []
