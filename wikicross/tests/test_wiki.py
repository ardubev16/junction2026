from wikicross.wiki import in_scripts, markdown, trailing_appendix


def test_markdown_converts_headings_and_drops_appendix_sections():
    extract = (
        "Intro.\n\n== Życie ==\nText.\n\n== Bibliografia ==\nBook, 1999.\n=== Artykuły ===\nArticle, 2001.\n\n"
        "== Upamiętnienie ==\nMore."
    )
    assert markdown("T", extract, {"Bibliografia"}) == "# T\nIntro.\n## Życie\nText.\n## Upamiętnienie\nMore."


def test_in_scripts_accepts_latin_and_cyrillic_but_not_other_scripts():
    assert in_scripts("Stepán Bandera, Łódź, Çanakkale")
    assert in_scripts("Степан Бандера")
    assert in_scripts("Урхо Кекконен (Urho Kekkonen) — президент Финляндии")  # Latin names inside Cyrillic
    assert not in_scripts("Ούρχο Κέκκονεν")  # Greek
    assert not in_scripts("أورهو كيكونن")  # Arabic


def test_trailing_appendix_drops_only_the_closing_run_of_appendix_sections():
    extract = (
        "Intro.\n== Views ==\nPolitical views.\n== Legacy ==\nText.\n== Notes ==\n\n"
        "== Bibliography ==\nBook, 1999.\n=== Articles ===\nArticle, 2001.\n== Links ==\nhttp://x\n"
    )
    classified = {"Views", "Notes", "Bibliography", "Links"}  # "Views" mistaken for an appendix name
    assert trailing_appendix(extract, classified) == {"Notes", "Bibliography", "Articles", "Links"}
