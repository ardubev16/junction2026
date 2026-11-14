from langdiff.app import sentences


def test_sentences_split_on_full_stops_but_not_finnish_dates_or_abbreviations():
    part = (
        "Kekkonen syntyi 3. syyskuuta 1900 Pielavedellä. Hänen poikansa Taneli (k. 1985) oli kansanedustaja.\n"
        "| Land | Stupade |\n| --- | --- |\n| Finland | 23 576 |\n"
        "- A list item. With two sentences.\n"
        "Short. This one is long enough to stand alone as a sentence."
    )
    assert sentences(part) == [
        "Kekkonen syntyi 3. syyskuuta 1900 Pielavedellä.",
        "Hänen poikansa Taneli (k. 1985) oli kansanedustaja.",
        "| Land | Stupade |",
        "| Finland | 23 576 |",
        "- A list item. With two sentences.",
        "Short. This one is long enough to stand alone as a sentence.",
    ]


def test_sentences_split_before_capitals_of_any_latin_alphabet():
    part = (
        "Bandera urodził się w Starym Uhrynowie w 1909 roku. Łączył działalność polityczną z terrorem.\n"
        "Za vlády Hitlera byl v roce 1941 zatčen. Často se o tom dodnes mluví v Česku."
    )
    assert sentences(part) == [
        "Bandera urodził się w Starym Uhrynowie w 1909 roku.",
        "Łączył działalność polityczną z terrorem.",
        "Za vlády Hitlera byl v roce 1941 zatčen.",
        "Často se o tom dodnes mluví v Česku.",
    ]
