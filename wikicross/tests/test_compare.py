from wikicross.compare import groups, vote


def test_groups_keep_one_sentence_per_language_instead_of_falling_back_to_pairs():
    # pl has two sentences; the chain de-pl1-fr-cs-pl2 would hold both. The closer pairs win: one
    # group of four editions instead of four pairs, then pl2-cs on its own (cs is taken in the group).
    de, pl1, fr, pl2, cs = ("de", 1, 1, 0), ("pl", 2, 1, 0), ("fr", 3, 1, 0), ("pl", 2, 1, 1), ("cs", 4, 1, 0)
    edges = [(de, pl1, 0.10), (pl1, fr, 0.12), (fr, cs, 0.15), (pl2, cs, 0.20), (de, cs, 0.50)]
    assert groups(edges, 0.40) == [([cs, de, fr, pl1], 0.15), ([cs, pl2], 0.20)]


def test_the_edition_contradicting_the_others_is_the_outlier():
    edges = {("fi", "sv"): False, ("fi", "en"): True, ("sv", "en"): True, ("en", "de"): True, ("fi", "de"): False}
    assert vote(edges) == {"verdict": "outlier", "outliers": ["en"],
                           "pairs": [["fi", "en"], ["sv", "en"], ["en", "de"]]}


def test_without_a_clear_outlier_the_editions_just_differ():
    assert vote({("fi", "en"): True}) == {"verdict": "differs", "outliers": [], "pairs": [["fi", "en"]]}
    # fi and en contradict each other, each also agrees with sv: one of two partners is not enough
    split = vote({("fi", "en"): True, ("fi", "sv"): False, ("en", "sv"): False})
    assert (split["verdict"], split["outliers"]) == ("differs", [])
    assert vote({("fi", "sv"): False, ("sv", "en"): False}) is None
