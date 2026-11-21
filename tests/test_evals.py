from wikicross import evals


def test_the_labelled_cases_are_well_formed():
    cases = evals.load()
    assert len({c["id"] for c in cases}) == len(cases)
    for c in cases:
        assert c["label"] in evals.LABELS, c["id"]
        assert len(c["passages"]) >= 2, c["id"]
        for p in c["passages"]:
            assert set(p) == {"lang", "heading", "text", "sentence"}, c["id"]
            assert p["sentence"] in p["text"], c["id"]  # the quote is part of its passage, as explain() assumes


def test_score_counts_a_translated_passage_and_a_missing_highlight():
    case = {
        "id": "x",
        "label": "differ",
        "passages": [
            {"lang": "fi", "heading": "", "text": "", "sentence": "Vuonna 1918."},
            {"lang": "sv", "heading": "", "text": "", "sentence": "År 1920."},
        ],
    }
    answer = {
        "discrepancy": True,
        "title": "t",
        "quotes": {
            "fi": {"english": "In <mark>1918</mark>.", "phrases": ["1918"]},
            "sv": {"english": "In 1920. And the whole passage around it, translated too.", "phrases": []},
        },
    }
    s = evals.score_explanation(case, answer)
    assert s["correct"]
    assert [(q["highlighted"], q["overlong"]) for q in s["quotes"]] == [(True, False), (False, True)]
