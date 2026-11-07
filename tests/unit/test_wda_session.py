"""iphone_mcp.wda's session handling. The unit tests run without the mcp SDK, so ToolError is stubbed."""
import importlib
import sys
import types

import pytest


@pytest.fixture
def wda(monkeypatch):
    exceptions = types.ModuleType("mcp.server.mcpserver.exceptions")
    exceptions.ToolError = type("ToolError", (Exception,), {})
    for name in ("mcp", "mcp.server", "mcp.server.mcpserver"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "mcp.server.mcpserver.exceptions", exceptions)
    monkeypatch.delitem(sys.modules, "iphone_mcp.wda", raising=False)
    module = importlib.import_module("iphone_mcp.wda")
    yield module
    sys.modules.pop("iphone_mcp.wda", None)


def fake_requests(monkeypatch, wda, responses):
    calls = []

    def request(method, path, body=None, timeout=30):
        calls.append(f"{method} {path}")
        resp = responses[f"{method} {path}"]
        if isinstance(resp, Exception):
            raise resp
        return resp

    monkeypatch.setattr(wda, "request", request)
    return calls


def test_joins_the_active_session(monkeypatch, wda):
    calls = fake_requests(monkeypatch, wda, {"GET /status": {"sessionId": "viewer"},
                                             "GET /session/viewer/x": {"value": 1}})
    assert wda.session("GET", "/x") == {"value": 1}
    assert "POST /session" not in calls


def test_stale_cached_session_joins_the_active_one(monkeypatch, wda):
    wda._sid = "old"
    calls = fake_requests(monkeypatch, wda, {
        "GET /session/old/x": wda.WDAError("invalid session id", "gone"),
        "GET /status": {"sessionId": "viewer"},
        "GET /session/viewer/x": {"value": 1},
    })
    assert wda.session("GET", "/x") == {"value": 1}
    assert "POST /session" not in calls


def test_opens_a_session_when_the_active_one_is_the_stale_one(monkeypatch, wda):
    wda._sid = "old"
    calls = fake_requests(monkeypatch, wda, {
        "GET /session/old/x": wda.WDAError("invalid session id", "gone"),
        "GET /status": {"sessionId": "old"},
        "POST /session": {"sessionId": "new"},
        "GET /session/new/x": {"value": 1},
    })
    assert wda.session("GET", "/x") == {"value": 1}
    assert calls[-2:] == ["POST /session", "GET /session/new/x"]
