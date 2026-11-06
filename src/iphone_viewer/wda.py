"""Minimal WebDriverAgent client for the viewer.

WebDriverAgent runs a single session: opening a new one ends the current one, which would break the MCP server's
session. So the client joins the session that is already active and only opens one when there is none.
"""
import json
import threading
import urllib.error
import urllib.request

SPRINGBOARD = "com.apple.springboard"


class WDAError(Exception):
    pass


class WDAClient:
    def __init__(self, base_url: str, timeout: float = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._sid: str | None = None
        self._lock = threading.Lock()

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                resp = json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                resp = json.loads(e.read())
            except ValueError:
                raise WDAError(f"HTTP {e.code}") from None
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise WDAError(f"WebDriverAgent not reachable at {self.base_url}: {e}") from None
        value = resp.get("value")
        if isinstance(value, dict) and "error" in value:
            raise WDAError(f"{value['error']}: {(value.get('message') or '').splitlines()[0]}")
        return resp

    def _open_session(self, join_existing: bool) -> str:
        if join_existing and (sid := self.request("GET", "/status").get("sessionId")):
            return sid
        resp = self.request("POST", "/session", {"capabilities": {"alwaysMatch": {}}})
        return resp.get("sessionId") or resp["value"]["sessionId"]

    def session_request(self, method: str, path: str, body: dict | None = None) -> dict:
        """Request within the session; if the session is gone (WebDriverAgent restarted), open a new one once."""
        with self._lock:
            for attempt in range(2):
                if self._sid is None:
                    self._sid = self._open_session(join_existing=attempt == 0)
                try:
                    return self.request(method, f"/session/{self._sid}{path}", body)
                except WDAError as e:
                    if attempt or "session" not in str(e):
                        raise
                    self._sid = None
        raise AssertionError("unreachable")

    def screen_size(self) -> tuple[float, float]:
        size = self.request("GET", "/wda/screen")["value"]["screenSize"]
        return size["width"], size["height"]

    def configure_stream(self, fps: int, scale_percent: int, quality: int) -> None:
        self.session_request("POST", "/appium/settings", {"settings": {
            "mjpegServerFramerate": fps,
            "mjpegScalingFactor": scale_percent,
            "mjpegServerScreenshotQuality": quality,
        }})

    def tap(self, x: float, y: float) -> None:
        self.session_request("POST", "/wda/tap", {"x": x, "y": y})

    def long_press(self, x: float, y: float, seconds: float) -> None:
        self.session_request("POST", "/wda/touchAndHold", {"x": x, "y": y, "duration": seconds})

    def swipe(self, x0: float, y0: float, x1: float, y1: float, ms: int) -> None:
        self.session_request("POST", "/actions", {"actions": [{
            "type": "pointer", "id": "finger1", "parameters": {"pointerType": "touch"},
            "actions": [
                {"type": "pointerMove", "duration": 0, "x": x0, "y": y0},
                {"type": "pointerDown", "button": 0},
                {"type": "pointerMove", "duration": ms, "x": x1, "y": y1},
                {"type": "pointerUp", "button": 0},
            ],
        }]})

    def type_text(self, text: str) -> None:
        self.session_request("POST", "/wda/keys", {"value": list(text)})

    def home(self) -> None:
        self.session_request("POST", "/wda/pressButton", {"name": "home"})

    def close_foreground_app(self) -> None:
        """Terminate the app in the foreground, like swiping it away in the app switcher."""
        bundle_id = self.request("GET", "/wda/activeAppInfo")["value"]["bundleId"]
        if bundle_id != SPRINGBOARD:
            self.session_request("POST", "/wda/apps/terminate", {"bundleId": bundle_id})
