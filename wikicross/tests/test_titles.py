from wikicross.app import representative


def test_representative_is_english_else_the_longest_edition():
    assert representative([("fi", "Talvisota", 90_000), ("en", "Winter War", 40_000)]) == ("en", "Winter War")
    assert representative([("fi", "Talvisota", 90_000), ("sv", "Vinterkriget", 120_000)]) == ("sv", "Vinterkriget")
