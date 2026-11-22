from wikicross.compare import groups, spread


def test_groups_keep_one_sentence_per_language_instead_of_falling_back_to_pairs():
    # pl has two sentences; the chain de-pl1-fr-cs-pl2 would hold both. The closer pairs win: one
    # group of four editions instead of four pairs, then pl2-cs on its own (cs is taken in the group).
    de, pl1, fr, pl2, cs = ("de", 1, 1, 0), ("pl", 2, 1, 0), ("fr", 3, 1, 0), ("pl", 2, 1, 1), ("cs", 4, 1, 0)
    edges = [(de, pl1, 0.10), (pl1, fr, 0.12), (fr, cs, 0.15), (pl2, cs, 0.20), (de, cs, 0.50)]
    assert groups(edges, 0.40) == [([cs, de, fr, pl1], 0.15), ([cs, pl2], 0.20)]


def test_spread_puts_the_most_different_items_first():
    fi, sv, en, ru, uk = ("fi",), ("sv",), ("en",), ("ru",), ("uk",)
    distance = {
        frozenset(p): d
        for p, d in [
            ((fi, sv), 0.1),
            ((fi, en), 0.1),
            ((sv, en), 0.1),
            ((fi, uk), 0.36),
            ((fi, ru), 0.35),
            ((ru, uk), 0.34),
            ((en, ru), 0.2),
        ]
    }
    assert spread([fi, sv, en, ru, uk], distance)[:3] == [fi, uk, ru]
