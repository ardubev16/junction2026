from wikicross import app, decide

TWO = [{"lang": "fi", "sentence": "a"}, {"lang": "sv", "sentence": "b"}]
THREE = [*TWO, {"lang": "en", "sentence": "c"}]


def test_a_decision_reads_kind_probability_strength_and_outlier_or_none_if_refused():
    factual = {"type": "choice", "choice": "factual", "probabilities": {"factual": 0.9, "none": 0.08}}
    strength = {"type": "score", "score": 1.5}
    answers = {
        "kind_0": factual,
        "strength_0": strength,
        "kind_1": {"type": "refusal"},
        "strength_1": strength,
        "kind_2": {"type": "choice", "choice": "contradiction"},  # not a criterion
        "strength_2": strength,
        "kind_3": factual,
        "strength_3": strength,
        "outlier_3": {"type": "choice", "choice": "en"},
        "kind_4": factual,
        "strength_4": strength,
        "outlier_4": {"type": "choice", "choice": "de"},  # not one of its quotes
    }
    assert decide.read(answers, 0, TWO) == {"kind": "factual", "real": 0.92, "strength": 1.5, "outlier": None}
    assert decide.read(answers, 1, TWO) is None
    assert decide.read(answers, 2, TWO) is None
    assert (decide.read(answers, 3, THREE) or {}).get("outlier") == "en"
    assert decide.read(answers, 4, THREE) is None
    assert decide.read(answers, 5, TWO) is None  # not answered at all


def finding(lang: str) -> dict:
    members = [{"lang": lang, "sentence": "a"}, {"lang": "sv", "sentence": "b"}, {"lang": "en", "sentence": "c"}]
    return {"members": members, "deviation": 2.0, "lang": lang, "outlier": True}  # the axis's outlier: lang


def test_judging_drops_no_disagreement_keeps_unchecked_ranks_the_strongest_first_and_names_the_outlier(monkeypatch):
    decisions = [
        {"kind": "none", "real": 0.01, "strength": 0.2, "outlier": None},
        {"kind": "bias", "real": 0.7, "strength": 0.5, "outlier": None},
        None,  # its batch failed
        {"kind": "factual", "real": 0.99, "strength": 1.8, "outlier": "en"},
    ]
    monkeypatch.setattr(decide, "decide", lambda *_: (decisions, "decision model error 502"))
    kept, error = app.judge([finding(lang) for lang in ("fi", "de", "fr", "et")], lambda *_: None)
    assert error == "decision model error 502"
    assert [f["members"][0]["lang"] for f in kept] == ["de", "fr", "et"]
    assert [f["kind"] for f in kept] == ["bias", None, "factual"]
    assert [(f["outlier"], f["lang"]) for f in kept] == [(False, "de"), (True, "fr"), (True, "en")]
    assert [f["members"][0]["lang"] for f in sorted(kept, key=lambda f: -app.rank(f))] == ["et", "de", "fr"]


def test_judged_pairs_sharing_a_sentence_and_kind_become_one_card_around_it():
    def member(lang: str, n: int = 0) -> dict:
        return {"lang": lang, "page_id": 1, "seq": 1, "n": n, "sentence": lang}

    def pair(other: str, kind: str, real: float) -> dict:
        d = {"kind": kind, "real": real, "strength": 1.0, "outlier": None}
        return {"members": [member("be"), member(other)], "kind": kind, "decision": d, "distance": real / 10}

    found = [pair("cs", "framing", 0.9), pair("it", "framing", 0.95), pair("nb", "factual", 0.8)]
    found.append({"members": [member("fi"), member("sv"), member("en")], "kind": "bias", "decision": None})
    out = app.merge_shared(found)
    assert [[m["lang"] for m in f["members"]] for f in out] == [["be", "it", "cs"], ["be", "nb"], ["fi", "sv", "en"]]
    f = out[0]
    assert (f["lang"], f["outlier"], f["decision"]["outlier"], f["distance"]) == ("be", True, "be", 0.095)
