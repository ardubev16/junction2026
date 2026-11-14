from langdiff.discrepancy import anchored_conflicts, conflicts, figure_slots, numbers


def test_numbers_read_every_languages_thousands_separator():
    assert numbers("25,904 dead; 23\u00a0576 stupade; 26 662 kuollutta; 1.200 tanks; 9 days") == {
        25904: ["25,904"],
        23576: ["23\u00a0576"],
        26662: ["26 662"],
        1200: ["1.200"],
    }


def test_big_differences_conflict_once_each_small_ones_are_dropped():
    en = "The Soviets lost 167,976 dead; earlier counts gave 126,875. Sweden sent 8,760 volunteers and 11,000 rifles."
    fi = "Neuvostoliitto menetti 126 875 kaatunutta. Ruotsista tuli 8 260 vapaaehtoista."
    # 126 875 is in both: no conflict. 8 260 pairs with 8,760 (6% apart, dropped), so not with 11,000.
    assert conflicts(en, fi) == []
    assert conflicts("Losses: 167,976 dead.", "Tappiot: 126 875 kaatunutta.") == [("167,976", "126 875")]


def test_years_and_shared_figures_are_never_conflicts():
    assert conflicts("Signed in 1940 by 300 delegates.", "Signed 1940 with 300 delegates.") == []
    assert conflicts("Elected in 1931.", "Elected in 1982.") == []


def test_passages_need_a_shared_number():
    en = "In 1940 there were 337,000 troops and 43,557 wounded."
    fi = "Vuonna 1940 joukkoja oli 460 000 ja haavoittuneita 43 557."
    assert anchored_conflicts(en, fi) == [("337,000", "460 000")]  # 43,557 anchors
    assert anchored_conflicts("There were 337,000 troops.", "Joukkoja oli 460 000.") == []  # nothing shared


def close(texts):
    return lambda a, b: conflicts(texts[a], texts[b])


def test_the_edition_against_the_majority_is_the_outlier():
    texts = {"fi": "Kaatuneita oli 126 875.", "sv": "Stupade: 126 875.", "en": "167,976 died."}
    assert figure_slots(texts, close(texts)) == [
        {"values": {"fi": "126 875", "sv": "126 875", "en": "167,976"}, "outliers": ["en"]}
    ]


def test_no_outlier_without_a_majority():
    two = {"fi": "Kaatuneita oli 126 875.", "en": "167,976 died."}
    assert figure_slots(two, close(two)) == [{"values": {"fi": "126 875", "en": "167,976"}, "outliers": []}]
    three = {"fi": "Lukuja: 200 000.", "sv": "Siffror: 300 000.", "en": "Figures: 250,000."}
    assert figure_slots(three, close(three))[0]["outliers"] == []
