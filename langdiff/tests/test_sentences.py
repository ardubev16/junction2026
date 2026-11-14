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
