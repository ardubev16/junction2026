from langdiff.compare import groups, merge_values
from langdiff.discrepancy import tally


def test_groups_keep_one_sentence_per_language_instead_of_falling_back_to_pairs():
    # pl has two sentences; the chain de-pl1-fr-cs-pl2 would hold both. The closer pairs win: one
    # group of four editions instead of four pairs, then pl2-cs on its own (cs is taken in the group).
    de, pl1, fr, pl2, cs = ("de", 1, 1, 0), ("pl", 2, 1, 0), ("fr", 3, 1, 0), ("pl", 2, 1, 1), ("cs", 4, 1, 0)
    edges = [(de, pl1, 0.10), (pl1, fr, 0.12), (fr, cs, 0.15), (pl2, cs, 0.20), (de, cs, 0.50)]
    assert groups(edges, 0.40) == [([cs, de, fr, pl1], 0.15), ([cs, pl2], 0.20)]


def finding(values, *langs):
    return {"kind": "value", "distance": 0.2, "change": 0.05, "slots": [tally(values)],
            "members": [{"lang": lang} for lang in langs]}


def test_findings_stating_the_same_figure_become_one_vote():
    a = finding({"hu": "350", "lt": "366"}, "hu", "lt")
    b = finding({"da": "366", "hu": "350"}, "da", "hu")
    other = finding({"hu": "350", "lt": "200"}, "hu", "lt")  # same hu value, another figure: kept apart
    clash = finding({"hu": "366", "nl": "350"}, "hu", "nl")  # hu states the other value here: kept apart
    merged = merge_values([a, b, other, clash])
    assert len(merged) == 3
    assert merged[0]["slots"][0]["votes"] == [{"value": "366", "langs": ["da", "lt"]}, {"value": "350", "langs": ["hu"]}]
    assert (merged[0]["slots"][0]["verdict"], merged[0]["slots"][0]["outliers"]) == ("outlier", ["hu"])
    assert [m["lang"] for m in merged[0]["members"]] == ["da", "hu", "lt"]


def test_a_pair_joins_the_vote_that_already_has_its_values():
    vote = finding({"sv": "100 000", "pl": "100 000", "ca": "70.000", "lt": "60.000"}, "sv", "ca", "lt", "pl")
    pair = finding({"ca": "70.000", "es": "100 000"}, "ca", "es")
    [merged] = merge_values([vote, pair])
    assert merged["slots"][0]["votes"][0] == {"value": "100 000", "langs": ["sv", "es", "pl"]}
    assert merged["slots"][0]["verdict"] == "contested"  # 3 of 5
