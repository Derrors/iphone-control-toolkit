import http.server
import io
import json
import threading
import urllib.request

import pytest

from iphone_viewer import wda as viewer_wda
from iphone_viewer.geometry import LongPress, Swipe, Tap, Viewport, classify
from iphone_viewer.mjpeg import iter_frames
from iphone_viewer.wda import WDAClient, WDAError


def part(jpeg, header=b"Content-Length"):
    return (b"--BoundaryString\r\nContent-type: image/jpeg\r\n" + header + b": %d\r\n\r\n" % len(jpeg)
            + jpeg + b"\r\n")


# ---- MJPEG ----

def test_frames_are_split_by_content_length():
    first, second = b"\xff\xd8one\r\n\r\nwith blank lines\xff\xd9", b"\xff\xd8two\xff\xd9"
    assert list(iter_frames(io.BytesIO(part(first) + part(second)))) == [first, second]


def test_header_name_is_case_insensitive():
    assert list(iter_frames(io.BytesIO(part(b"jpeg", header=b"content-length")))) == [b"jpeg"]


def test_truncated_last_frame_is_dropped():
    stream = part(b"complete") + part(b"truncated")[:-8]
    assert list(iter_frames(io.BytesIO(stream))) == [b"complete"]


def test_empty_stream_yields_nothing():
    assert list(iter_frames(io.BytesIO(b""))) == []


# ---- geometry ----

def test_tall_window_letterboxes_vertically():
    v = Viewport.fit(393, 852, 393 * 2, 852 * 2 + 100)
    assert (v.scale, v.width, v.height, v.x, v.y) == (2, 786, 1704, 0, 50)


def test_wide_window_centers_horizontally():
    v = Viewport.fit(393, 852, 1000, 852)
    assert (v.scale, v.width, v.x, v.y) == (1, 393, (1000 - 393) // 2, 0)


def test_pixels_map_back_to_points():
    v = Viewport.fit(393, 852, 393 * 2, 852 * 2 + 100)
    assert v.to_points(v.x + 200, v.y + 300) == (100, 150)


def test_presses_outside_the_screen_are_clamped():
    v = Viewport.fit(393, 852, 1000, 852)
    assert v.to_points(0, -5) == (0, 0)
    assert v.to_points(999, 2000) == (393, 852)


def test_short_still_press_is_a_tap():
    assert classify((10, 10), (12, 13), 0.1) == Tap(10, 10)


def test_long_still_press_is_a_long_press():
    assert classify((10, 10), (10, 10), 1.2) == LongPress(10, 10, 1.2)


def test_moving_press_is_a_swipe_with_clamped_duration():
    assert classify((100, 700), (100, 200), 0.05) == Swipe(100, 700, 100, 200, 100)
    assert classify((100, 700), (100, 200), 5) == Swipe(100, 700, 100, 200, 800)
    assert classify((100, 700), (100, 200), 0.3).ms == 300


# ---- WDA session handling ----

class FakeWDA(WDAClient):
    """Records requests; `responses` maps "METHOD path" to a response dict or an exception."""

    def __init__(self, responses):
        super().__init__("http://wda")
        self.responses, self.calls = responses, []

    def request(self, method, path, body=None):
        self.calls.append(f"{method} {path}")
        resp = self.responses[f"{method} {path}"]
        if isinstance(resp, list):
            resp = resp.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


def test_joins_the_active_session_instead_of_replacing_it():
    wda = FakeWDA({"GET /status": {"sessionId": "mcp"}, "POST /session/mcp/wda/tap": {"value": None}})
    wda.tap(1, 2)
    assert wda.calls == ["GET /status", "POST /session/mcp/wda/tap"]


def test_opens_a_session_when_none_is_active():
    wda = FakeWDA({"GET /status": {"value": {}}, "POST /session": {"sessionId": "new"},
                   "POST /session/new/wda/tap": {"value": None}})
    wda.tap(1, 2)
    assert "POST /session" in wda.calls


def test_stale_session_is_replaced_once():
    wda = FakeWDA({
        "GET /status": {"sessionId": "stale"},
        "POST /session/stale/wda/tap": WDAError("invalid session id: gone"),
        "POST /session": {"sessionId": "fresh"},
        "POST /session/fresh/wda/tap": {"value": None},
    })
    wda.tap(1, 2)
    assert wda.calls[-2:] == ["POST /session", "POST /session/fresh/wda/tap"]


def test_other_errors_are_not_retried():
    wda = FakeWDA({"GET /status": {"sessionId": "s"},
                   "POST /session/s/wda/tap": WDAError("no such element: x")})
    with pytest.raises(WDAError):
        wda.tap(1, 2)
    assert wda.calls.count("POST /session/s/wda/tap") == 1


def test_close_app_leaves_the_home_screen_alone():
    wda = FakeWDA({"GET /wda/activeAppInfo": {"value": {"bundleId": "com.apple.springboard"}}})
    wda.close_foreground_app()
    assert wda.calls == ["GET /wda/activeAppInfo"]


class SimulatedWDA:
    """WebDriverAgent's session rule: one active session, and opening a new one ends it."""

    def __init__(self):
        self.active, self.opened = None, 0

    def open(self):
        self.opened += 1
        self.active = f"s{self.opened}"
        return {"sessionId": self.active}

    def restart(self):
        self.active = None

    def request(self, method, path, body=None):
        if path == "/status":
            return {"sessionId": self.active}
        if path == "/session":
            return self.open()
        if path.split("/")[2] != self.active:
            raise WDAError("invalid session id: gone")
        return {"value": None}


class ClientOf(WDAClient):
    def __init__(self, wda):
        super().__init__("http://wda")
        self.wda = wda

    def request(self, method, path, body=None):
        return self.wda.request(method, path, body)


def test_stale_cached_session_joins_the_new_active_one():
    wda = SimulatedWDA()
    client = ClientOf(wda)
    client.tap(1, 2)
    wda.restart()
    wda.open()  # another client got here first
    client.tap(1, 2)
    assert client._sid == wda.active == "s2"
    assert wda.opened == 2


def test_clients_do_not_end_each_others_sessions_after_a_restart():
    wda = SimulatedWDA()
    a, b = ClientOf(wda), ClientOf(wda)
    a.tap(1, 2)
    b.tap(1, 2)
    wda.restart()
    opened_before = wda.opened
    for _ in range(5):
        a.tap(1, 2)
        b.tap(1, 2)
    assert wda.opened == opened_before + 1


# ---- errors and proxies ----

def test_error_without_message_is_a_wda_error(monkeypatch):
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

    body = json.dumps({"value": {"error": "unknown error", "message": ""}}).encode()
    monkeypatch.setattr(viewer_wda, "open_direct", lambda *a, **k: Response(body))
    with pytest.raises(WDAError, match="unknown error"):
        WDAClient("http://wda").request("GET", "/x")


def test_requests_to_the_phone_ignore_the_hosts_proxy(monkeypatch):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"value": {"screenSize": {"width": 393, "height": 852}}}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.setattr(urllib.request, "_opener", None)  # urlopen caches the proxy settings it first saw
    try:
        assert WDAClient(f"http://127.0.0.1:{server.server_port}").screen_size() == (393, 852)
    finally:
        server.shutdown()
        server.server_close()
