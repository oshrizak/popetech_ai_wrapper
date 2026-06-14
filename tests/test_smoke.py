"""Offline unit tests for the Pope Tech wrapper (no network required).

These use a fake ``requests.Session`` so the transport, pagination, error
mapping, and safe_mode guard can be tested without hitting the live API.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from pope_tech import (
    AuthenticationError,
    NotFoundError,
    PopeTechClient,
    SafeModeError,
    ValidationError,
)
from pope_tech.http import Transport, _extract_items


class FakeResponse:
    def __init__(self, status_code=200, body=None, headers=None, content=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {"Content-Type": "application/json"}
        if content is not None:
            self.content = content
        else:
            self.content = json.dumps(body).encode() if body is not None else b""
        self.url = "https://api.pope.tech/test"
        self.request = SimpleNamespace(method="GET")

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body

    @property
    def text(self):
        return json.dumps(self._body) if self._body is not None else ""


class FakeSession:
    """Records calls and returns queued responses (or one repeated response)."""

    def __init__(self, responses):
        self.headers = {}
        self._responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if len(self._responses) == 1:
            return self._responses[0]
        return self._responses.pop(0)

    def close(self):
        pass


def make_transport(responses, **kwargs):
    session = FakeSession(responses if isinstance(responses, list) else [responses])
    return Transport("test-token", session=session, **kwargs), session


# -- token resolution ------------------------------------------------------


def test_token_from_env(monkeypatch):
    monkeypatch.setenv("POPE_TECH_API_KEY", "env-token")
    t = Transport(session=FakeSession([FakeResponse(body={})]))
    assert t.session.headers["Authorization"] == "Bearer env-token"


def test_missing_token_raises(monkeypatch):
    for key in ("POPE_TECH_API_KEY", "POPETECH_API_KEY", "POPE_TECH_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(Exception):
        Transport(session=FakeSession([]))


# -- requests + errors -----------------------------------------------------


def test_get_returns_parsed_json():
    t, _ = make_transport(FakeResponse(body={"data": {"ok": True}}))
    assert t.get("/me") == {"data": {"ok": True}}


def test_drops_none_query_params():
    t, session = make_transport(FakeResponse(body={}))
    t.get("/x", params={"a": 1, "b": None})
    assert session.calls[0][2]["params"] == {"a": 1}


@pytest.mark.parametrize(
    "status,exc",
    [(401, AuthenticationError), (404, NotFoundError), (422, ValidationError)],
)
def test_status_maps_to_exception(status, exc):
    body = {"message": "boom", "errors": {"field": ["bad"]}}
    t, _ = make_transport(FakeResponse(status_code=status, body=body), max_retries=0)
    with pytest.raises(exc):
        t.get("/x")


def test_validation_error_exposes_fields():
    body = {"message": "bad", "errors": {"full_url": ["required"]}}
    t, _ = make_transport(FakeResponse(status_code=422, body=body), max_retries=0)
    with pytest.raises(ValidationError) as ei:
        t.post("/x", json={})
    assert ei.value.errors == {"full_url": ["required"]}


def test_retries_on_500_then_succeeds():
    responses = [
        FakeResponse(status_code=500, body={"message": "err"}),
        FakeResponse(status_code=200, body={"data": 1}),
    ]
    t, session = make_transport(responses, max_retries=2)
    # Patch sleep so the test is instant.
    import pope_tech.http as h

    h.time.sleep = lambda *_: None
    assert t.get("/x") == {"data": 1}
    assert len(session.calls) == 2


# -- safe_mode -------------------------------------------------------------


def test_safe_mode_blocks_writes():
    t, session = make_transport(FakeResponse(body={}), safe_mode=True)
    with pytest.raises(SafeModeError):
        t.post("/x", json={})
    assert session.calls == []  # never hit the network


def test_safe_mode_allows_reads():
    t, _ = make_transport(FakeResponse(body={"data": 1}), safe_mode=True)
    assert t.get("/x") == {"data": 1}


# -- pagination ------------------------------------------------------------


def test_extract_items_from_list():
    items, pag = _extract_items([1, 2, 3])
    assert items == [1, 2, 3] and pag is None


def test_extract_items_from_envelope():
    body = {"data": [{"id": 1}], "meta": {"pagination": {"last_page": 2}}}
    items, pag = _extract_items(body)
    assert items == [{"id": 1}] and pag == {"last_page": 2}


def test_extract_items_nested_list():
    body = {"data": {"tree": [{"id": 1}, {"id": 2}]}}
    items, _ = _extract_items(body)
    assert items == [{"id": 1}, {"id": 2}]


def test_paginate_follows_pages():
    page1 = FakeResponse(
        body={"data": [1, 2], "meta": {"pagination": {"current_page": 1, "last_page": 2}}}
    )
    page2 = FakeResponse(
        body={"data": [3], "meta": {"pagination": {"current_page": 2, "last_page": 2}}}
    )
    t, _ = make_transport([page1, page2])
    assert list(t.paginate("/things", page_size=2)) == [1, 2, 3]


def test_paginate_respects_max_items():
    page = FakeResponse(
        body={"data": [1, 2, 3, 4], "meta": {"pagination": {"current_page": 1, "last_page": 9}}}
    )
    t, _ = make_transport(page)
    assert list(t.paginate("/things", max_items=2)) == [1, 2]


# -- client wiring ---------------------------------------------------------


def test_client_resource_namespaces():
    client = PopeTechClient(token="x")
    for attr in (
        "account", "organizations", "groups", "users", "websites",
        "scans", "scan_containers", "crawls", "reports", "dashboard", "tokens",
    ):
        assert hasattr(client, attr)


def test_client_org_required_error():
    client = PopeTechClient(token="x")
    with pytest.raises(Exception):
        client.websites.list()  # no org set
