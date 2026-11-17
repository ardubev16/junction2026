from wikicross.app import MIN_CHARS, split


def test_split_merges_paragraphs_and_skips_reference_sections():
    long = "x" * MIN_CHARS
    text = (
        "Intro one.\n"
        "Intro two.\n"
        "## History\n"
        "Pääartikkeli: Something\n"
        f"{long}\n"
        "short tail\n"
        "## References\n"
        "- a source\n"
        "### Books\n"
        "- a book\n"
        "## Legacy\n"
        "Still here."
    )
    assert split(text) == [
        ("", "Intro one.\nIntro two."),
        ("History", long),
        ("History", "short tail"),
        ("Legacy", "Still here."),
    ]
