import ipaddress
from collections import defaultdict, deque

from fastapi.testclient import TestClient

from wikicross import app as m


def test_outside_clients_are_limited_allowed_ones_are_not(monkeypatch):
    monkeypatch.setattr(m.settings, "rate_limit", True)
    monkeypatch.setattr(m.settings, "allowed_ips", [ipaddress.ip_network("10.0.0.0/8")])
    monkeypatch.setattr(m, "_hits", defaultdict(deque))
    outside = TestClient(m.app, client=("203.0.113.9", 1))  # not a context manager: no lifespan, no DB
    inside = TestClient(m.app, client=("10.1.2.3", 1))

    # {} fails validation (422) before any LLM call, but still counts.
    codes = [outside.post("/api/translate", json={}).status_code for _ in range(30)]
    assert codes == [422] * 30
    r = outside.post("/api/translate", json={})
    assert r.status_code == 429
    assert 1 <= int(r.headers["retry-after"]) <= 61
    assert outside.get("/api/progress?title=x").status_code == 200  # polled each second: never limited
    assert all(inside.post("/api/translate", json={}).status_code == 422 for _ in range(40))


def test_no_limit_when_off(monkeypatch):
    monkeypatch.setattr(m.settings, "rate_limit", False)
    monkeypatch.setattr(m, "_hits", defaultdict(deque))
    outside = TestClient(m.app, client=("203.0.113.9", 1))
    assert all(outside.post("/api/translate", json={}).status_code == 422 for _ in range(40))
    assert outside.get("/api/limits").json() is None
