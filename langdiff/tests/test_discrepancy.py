from langdiff.discrepancy import anchored_conflicts, conflicts, numbers


def test_numbers_read_every_languages_thousands_separator():
    assert numbers("25,904 dead; 23\u00a0576 stupade; 26 662 kuollutta; 1.200 tanks; 9 days") == {
        25904: ["25,904"],
        23576: ["23\u00a0576"],
        26662: ["26 662"],
        1200: ["1.200"],
    }


def test_close_figures_conflict_once_each():
    en = "Helsinki announced 19,576 dead; revised estimates give 25,904. Sweden sent 8,760 volunteers."
    sv = "Finland: 23 576 stupade. Cirka 8 260 svenska frivilliga."
    # 23 576 is matched to its closest figure only; 19,576 stays unmatched rather than conflicting too.
    assert conflicts(en, sv, 0.29) == [("8,760", "8 260"), ("25,904", "23 576")]


def test_shared_figures_and_far_apart_years_are_not_conflicts():
    assert conflicts("Signed in 1940 by 300 delegates.", "Signed 1940 with 300 delegates.", 0.2) == []
    assert conflicts("Born in 1900, president from 1956.", "President 1982.", 0.2) == []


def test_years_need_closely_matching_passages():
    assert conflicts("Elected in 1981.", "Elected in 1982.", 0.25) == [("1981", "1982")]
    assert conflicts("Elected in 1981.", "Elected in 1982.", 0.33) == []


def test_passages_need_a_shared_number_and_never_conflict_on_years():
    en = "In 1978 he won 259 of the 300 electoral votes; first elected in 1956."
    fi = "Vuoden 1978 vaaleissa hän sai 260 valitsijamiestä; valittiin 1955."
    assert anchored_conflicts(en, fi) == [("259", "260")]  # 1978 anchors; 1956 vs 1955 is ignored
    assert anchored_conflicts("He won 259 votes.", "Hän sai 260 ääntä.") == []  # nothing shared
