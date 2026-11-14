from langdiff.wiki import is_latin, markdown, trailing_appendix


def test_markdown_converts_headings_and_drops_appendix_sections():
    extract = (
        "Intro.\n\n== Życie ==\nText.\n\n== Bibliografia ==\nBook, 1999.\n=== Artykuły ===\nArticle, 2001.\n\n"
        "== Upamiętnienie ==\nMore."
    )
    assert markdown("T", extract, {"Bibliografia"}) == "# T\nIntro.\n## Życie\nText.\n## Upamiętnienie\nMore."


def test_is_latin_rejects_cyrillic_and_accepts_accented_latin():
    assert not is_latin("Степан Бандера")
    assert is_latin("Stepán Bandera, Łódź, Çanakkale")


def test_trailing_appendix_drops_only_the_closing_run_of_appendix_sections():
    extract = (
        "Intro.\n== Views ==\nPolitical views.\n== Legacy ==\nText.\n== Notes ==\n\n"
        "== Bibliography ==\nBook, 1999.\n=== Articles ===\nArticle, 2001.\n== Links ==\nhttp://x\n"
    )
    classified = {"Views", "Notes", "Bibliography", "Links"}  # "Views" mistaken for an appendix name
    assert trailing_appendix(extract, classified) == {"Notes", "Bibliography", "Articles", "Links"}
