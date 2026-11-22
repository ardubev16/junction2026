from statistics import fmean

from wikicross.app import narrow


def deviations(z):
    return {lang: zl - fmean(v for other, v in z.items() if other != lang) for lang, zl in z.items()}


def finding(z):
    d = deviations(z)
    lang = max(d, key=lambda k: abs(d[k]))
    return {
        "lang": lang,
        "deviation": d[lang],
        "deviations": {k: round(v, 2) for k, v in d.items()},
        "outlier": len(z) >= 3,
        "members": [{"lang": k} for k in z],
        "axis": "certainty",
    }


def test_narrow_matches_a_recompute_on_the_kept_editions():
    z = {"fi": 2.5, "sv": 0.3, "de": -0.4, "ru": -1.9}  # positions on the axis, in σ
    [f] = narrow([finding(z)], {"fi", "sv", "ru"})
    expected = deviations({k: z[k] for k in ("fi", "sv", "ru")})
    assert f["lang"] == "fi"
    assert abs(f["deviation"] - expected["fi"]) < 0.02
    assert f["deviations"].keys() == expected.keys()
    assert f["outlier"] is True
    assert [m["lang"] for m in f["members"]] == ["fi", "sv", "ru"]


def test_narrow_drops_findings_left_with_one_edition_or_under_the_threshold():
    assert narrow([finding({"fi": 2.5, "sv": 0.3, "de": -0.4})], {"fi", "en"}) == []
    # fi stands out only against ru: without ru, fi and sv sit 0.6σ apart
    assert narrow([finding({"fi": 0.5, "sv": -0.1, "ru": -3.0})], {"fi", "sv"}) == []


def test_narrow_keeps_a_statement_many_editions_make_whatever_its_tone():
    # As differences(): with compare.BIG_GROUP editions or more a group is a candidate under the threshold.
    z = {lang: 0.1 * i for i, lang in enumerate(["fi", "sv", "en", "de", "fr", "it", "es", "ru", "uk", "pl"])}
    assert len(narrow([finding(z)], set(z) - {"pl"})) == 1
    assert narrow([finding(z)], {"fi", "sv", "en"}) == []
