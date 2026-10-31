"""WebDriverAgent HTTP 客户端:请求、会话、屏幕尺寸。"""
import json
import urllib.error
import urllib.request

from mcp.server.mcpserver.exceptions import ToolError

from . import config

# 容器里可能设了 HTTP_PROXY,访问本机 WDA 不能走代理
_http = urllib.request.build_opener(urllib.request.ProxyHandler({}))


# 只有 ToolError 的内容会透传给客户端,其他异常只显示一句笼统的报错
class WDAUnavailable(ToolError):
    pass


class WDAError(ToolError):
    def __init__(self, error, message):
        super().__init__(f"{error}: {message}")
        self.error = error


def request(method, path, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(config.WDA_URL + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with _http.open(req, timeout=timeout) as r:
            resp = json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            resp = json.loads(e.read())
        except ValueError:
            raise WDAError("http", e.code) from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise WDAUnavailable(
            f"WDA 不可用({e}),supervisor 一般 1~2 分钟内会拉起;截图/点击/滑动/按键可照常用") from None
    value = resp.get("value")
    if isinstance(value, dict) and "error" in value:
        raise WDAError(value["error"], (value.get("message") or "").splitlines()[0])
    return resp


_sid = None


def session(method, path, body=None, timeout=30):
    """带会话的 WDA 请求;WDA 重启后旧会话失效,自动重建一次。"""
    global _sid
    for attempt in range(2):
        if _sid is None:
            r = request("POST", "/session", {"capabilities": {"alwaysMatch": {}}})
            _sid = r.get("sessionId") or r["value"]["sessionId"]
        try:
            return request(method, f"/session/{_sid}{path}", body, timeout)
        except WDAError as e:
            if attempt == 0 and "session" in e.error:
                _sid = None
                continue
            raise


_screen_size = None


def screen():
    """屏幕尺寸(点)。WDA 不可用时用环境变量或上次缓存,都没有就报错,免得按错的尺寸换算坐标。"""
    global _screen_size
    if _screen_size is None:
        try:
            s = request("GET", "/wda/screen")["value"]["screenSize"]
            _screen_size = (int(s["width"]), int(s["height"]))
            config.save_screen(_screen_size)
        except (WDAUnavailable, WDAError, KeyError):
            fallback = config.fallback_screen()
            if fallback is None:
                raise ToolError("WDA 不可用,也不知道屏幕尺寸;等 WDA 起来一次,或在 .env 里设 SCREEN_W/SCREEN_H") from None
            return fallback
    return _screen_size


def locked():
    return bool(request("GET", "/wda/locked", timeout=10)["value"])


def touch(points, pause_ms=0):
    """一个 W3C 触摸手势:依次经过 points [(x, y, 毫秒)],按下后可停 pause_ms。"""
    (x0, y0, _), rest = points[0], points[1:]
    actions = [{"type": "pointerMove", "duration": 0, "x": x0, "y": y0},
               {"type": "pointerDown", "button": 0}]
    if pause_ms:
        actions.append({"type": "pause", "duration": pause_ms})
    actions += [{"type": "pointerMove", "duration": ms, "x": x, "y": y} for x, y, ms in rest]
    actions.append({"type": "pointerUp", "button": 0})
    session("POST", "/actions", {"actions": [{
        "type": "pointer", "id": "finger1", "parameters": {"pointerType": "touch"}, "actions": actions}]})
