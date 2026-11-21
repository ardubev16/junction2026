from wikicross import app, decide


def test_a_decision_reads_kind_probability_and_strength_or_none_if_refused():
    answers = {
        "kind_0": {"type": "choice", "choice": "factual", "probabilities": {"factual": 0.9, "none": 0.08}},
        "strength_0": {"type": "score", "score": 1.5},
        "kind_1": {"type": "refusal"},
        "strength_1": {"type": "score", "score": 1.0},
        "kind_2": {"type": "choice", "choice": "contradiction"},  # not a criterion
        "strength_2": {"type": "score", "score": 1.0},
    }
    assert decide.read(answers, 0) == {"kind": "factual", "real": 0.92, "strength": 1.5}
    assert decide.read(answers, 1) is None
    assert decide.read(answers, 2) is None
    assert decide.read(answers, 3) is None  # not answered at all


def finding(lang: str) -> dict:
    return {"members": [{"lang": lang, "sentence": "a"}, {"lang": "sv", "sentence": "b"}], "deviation": 2.0}


def test_judging_drops_no_disagreement_keeps_unchecked_and_ranks_the_strongest_first(monkeypatch):
    decisions = [
        {"kind": "none", "real": 0.01, "strength": 0.2},
        {"kind": "bias", "real": 0.7, "strength": 0.5},
        None,  # its batch failed
        {"kind": "factual", "real": 0.99, "strength": 1.8},
    ]
    monkeypatch.setattr(decide, "decide", lambda *_: (decisions, "decision model error 502"))
    kept, error = app.judge([finding(lang) for lang in ("fi", "de", "fr", "et")], lambda *_: None)
    assert error == "decision model error 502"
    assert [f["members"][0]["lang"] for f in kept] == ["de", "fr", "et"]
    assert [f["kind"] for f in kept] == ["bias", None, "factual"]
    assert [f["members"][0]["lang"] for f in sorted(kept, key=lambda f: -app.rank(f))] == ["et", "de", "fr"]
