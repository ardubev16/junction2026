import httpx
import pytest
from fastapi import HTTPException

from wikicross import translator


def fake_azure(monkeypatch, translate):
    """Azure's /translate answering each item with translate(its HTML); returns the request bodies."""
    sent = []

    def post(url, params, headers, json, timeout):  # noqa: ARG001 (httpx.post's own names)
        sent.append(json)
        return httpx.Response(200, json=[{"translations": [{"text": translate(i["Text"]), "to": "en"}]} for i in json])

    monkeypatch.setenv("AZURE_TRANSLATOR_KEY", "k")
    monkeypatch.setattr(translator.httpx, "post", post)
    return sent


def test_marks_and_line_breaks_survive_and_article_text_is_not_html(monkeypatch):
    sent = fake_azure(monkeypatch, lambda h: h.replace("sota", "war").replace("<br>", "<br/>"))
    text = "Talvi < kesä & <mark>sota</mark>\n* toinen rivi"
    assert translator.request([text]) == ["Talvi < kesä & <mark>war</mark>\n* toinen rivi"]
    assert sent[0][0]["Text"] == "Talvi &lt; kesä &amp; <mark>sota</mark><br>* toinen rivi"


def test_requests_are_split_at_azures_size_limit(monkeypatch):
    sent = fake_azure(monkeypatch, str.upper)
    texts = ["a" * 30_000, "b" * 30_000, "c"]
    assert translator.request(texts) == ["A" * 30_000, "B" * 30_000, "C"]
    assert [len(body) for body in sent] == [1, 2]


def test_no_key_says_which_variable(monkeypatch):
    monkeypatch.delenv("AZURE_TRANSLATOR_KEY", raising=False)
    with pytest.raises(HTTPException, match="AZURE_TRANSLATOR_KEY"):
        translator.request(["x"])
