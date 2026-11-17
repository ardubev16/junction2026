import pytest

from wikicross import wiki
from wikicross.wiki import WikiError, ensure_editions, in_scripts, markdown, trailing_appendix


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


class FakeCursor:
    """Just enough of a pymysql cursor for ensure_editions: no topic marked yet, no edition stored."""

    def __init__(self):
        self.sql = []
        self.connection = self

    def execute(self, sql, args=None):
        self.sql.append((sql, args))

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def begin(self):
        pass

    def commit(self):
        pass


def page_of(fail_lang):
    """wiki.page for a topic Q1 in en, fi and sv, where fetching `fail_lang` fails."""
    def page(host, title, text):
        lang = host.split(".")[0]
        if text and lang == fail_lang:
            raise WikiError(f"{host}: HTTP 429")
        links = [("fi", "https://fi.wikipedia.org/wiki/Talvisota", "Talvisota"),
                 ("sv", "https://sv.wikipedia.org/wiki/Vinterkriget", "Vinterkriget")]
        return {"page_id": len(lang), "title": title, "url": f"https://{host}/wiki/{title}", "wikidata_id": "Q1",
                "langlinks": links, "extract": "Text of the article."}
    return page


@pytest.mark.parametrize("fail_lang, marked", [("sv", False), (None, True)])
def test_a_topic_is_marked_fetched_only_when_no_edition_failed(monkeypatch, fail_lang, marked):
    # A topic marked fetched is never fetched again: one throttled edition must leave it unmarked.
    monkeypatch.setattr(wiki, "page", page_of(fail_lang))
    monkeypatch.setattr(wiki, "appendix_headings", lambda texts: set())
    cur = FakeCursor()
    ensure_editions(cur, "Q1", "en.wikipedia.org", "Winter War", "en")
    stored = {args[0] for sql, args in cur.sql if sql.startswith("INSERT IGNORE INTO article ")}
    assert stored == ({"en", "fi"} if fail_lang else {"en", "fi", "sv"})
    assert any(sql.startswith("INSERT INTO topic_editions") for sql, _ in cur.sql) is marked
