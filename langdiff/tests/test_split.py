from langdiff.app import MIN_CHARS, split


def test_split_merges_paragraphs_and_skips_reference_sections():
    long = "x" * MIN_CHARS
    text = "\n".join([
        "Intro one.", "Intro two.",
        "## History", "Pääartikkeli: Something", long, "short tail",
        "## References", "- a source",
        "### Books", "- a book",
        "## Legacy", "Still here.",
    ])
    assert split(text) == [
        ("", "Intro one.\nIntro two."),
        ("History", long),
        ("History", "short tail"),
        ("Legacy", "Still here."),
    ]
