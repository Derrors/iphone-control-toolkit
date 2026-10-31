"""MCP 工具定义(stdio)。

主路线走 WebDriverAgent;WDA 不可用时,截图/点击/滑动/按键/英文输入退回 CoreDevice HID。
坐标一律用「点」(pt),和 iphone_screenshot 返回图像的像素一一对应。
"""
import base64
import subprocess
import tempfile
import time
from functools import cache

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import apps, config, elements, hid, imaging, wda
from .unlock import ensure_unlocked

mcp = MCPServer(
    "iphone",
    instructions=(
        "控制一台通过 USB 连接的真实 iPhone。坐标单位是点(pt),与 iphone_screenshot 图像像素一致。"
        "操作前先用 iphone_screenshot 或 iphone_list_elements 看清屏幕;能按名字点就优先用 iphone_tap_element。"
        "游戏、地图等界面没有元素树,只能看截图按坐标操作;小图标、小字看不清时用 iphone_screenshot 的区域放大。"
        "配置了锁屏密码时,各操作工具会先自动解锁。每次操作后再截图确认结果。"
        "涉及付款、删除、发送消息、修改账号或隐私设置的操作,先向用户确认。"
    ),
)


def _elements():
    xml = wda.request("GET", f"/source?format=xml&excluded_attributes={elements.SOURCE_EXCLUDED}",
                      timeout=60)["value"]
    return elements.parse_source(xml, wda.screen())


def _ios(*args, timeout=60):
    try:
        r = subprocess.run([config.IOS, *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ToolError(f"go-ios 超时({timeout} 秒)") from None
    if r.returncode:
        err = r.stderr.strip().splitlines()
        raise ToolError(f"go-ios 失败: {err[-1] if err else r.returncode}")
    return r.stdout


@cache
def _apps(include_system):
    return apps.parse_apps(_ios("apps", *(["--system"] if include_system else [])))


def _resolve_app(app):
    bid = apps.resolve(app, [lambda: _apps(False), lambda: _apps(True)])
    if bid is None:
        raise ToolError(f'找不到名为 "{app}" 的 App,用 iphone_list_apps 查看')
    return bid


@mcp.tool(structured_output=False)
def iphone_status() -> str:
    """查看连接状态:WDA 是否就绪、是否锁屏、当前前台 App、屏幕尺寸。"""
    try:
        ready = wda.request("GET", "/status", timeout=5)["value"].get("ready")
        app = wda.request("GET", "/wda/activeAppInfo", timeout=10)["value"].get("bundleId")
        w, h = wda.screen()
        if not wda.locked():
            lock = "未锁屏"
        elif config.PASSCODE_FILE.exists():
            lock = "已锁屏(操作时会自动解锁)"
        else:
            lock = "已锁屏(未配置自动解锁,需要人工解锁)"
        if config.UNLOCK_GUARD.exists():
            lock += ";自动解锁已停用"
        return f"WDA 就绪: {ready}\n锁屏: {lock}\n前台 App: {app}\n屏幕: {w}x{h} 点"
    except (wda.WDAUnavailable, wda.WDAError) as e:
        return f"{e}\n读界面元素、按名字点击、启动 App、输入中文要等 WDA 恢复"


@mcp.tool(structured_output=False)
def iphone_screenshot(x: float | None = None, y: float | None = None,
                      width: float | None = None, height: float | None = None) -> list:
    """截取当前屏幕。图像已缩放到点尺寸,像素坐标可直接用于点击和滑动。

    看不清小图标、小字时,传 x/y/width/height(点)放大这块区域:从原始高清截图裁剪,
    小区域再额外放大。返回文字里有放大倍数,图中坐标换算回屏幕点:x + 像素/倍数。
    """
    region = (x, y, width, height)
    if any(v is not None for v in region) and None in region:
        raise ToolError("放大区域要同时给出 x、y、width、height")
    ensure_unlocked()
    try:
        png = base64.b64decode(wda.request("GET", "/screenshot")["value"])
        via = "WDA"
    except wda.WDAUnavailable:
        with tempfile.NamedTemporaryFile(suffix=".png") as f:
            hid.run("screen-capture", "screenshot", f.name)
            png = open(f.name, "rb").read()
        via = "HID"
    screen = wda.screen()
    if x is None:
        jpeg, (w, h) = imaging.full_screen_jpeg(png, screen)
        return [Image(data=jpeg, format="jpeg"), f"{w}x{h} 点,图像像素即点坐标(经 {via})"]
    try:
        jpeg, (x1, y1, rw, rh), zoom = imaging.region_jpeg(png, screen, x, y, width, height)
    except ValueError as e:
        raise ToolError(str(e)) from None
    return [Image(data=jpeg, format="jpeg"),
            f"区域 ({x1:g},{y1:g}) 起 {rw:g}x{rh:g} 点,放大 {zoom:.3g} 倍;"
            f"图中像素 (u,v) 对应屏幕点 ({x1:g}+u/{zoom:.3g}, {y1:g}+v/{zoom:.3g})(经 {via})"]


@mcp.tool(structured_output=False)
def iphone_list_elements(filter: str = "", limit: int = 150) -> str:
    """列出屏幕上带文字的界面元素:类型、标签、中心点坐标、尺寸。

    filter: 只返回标签/名字/值里包含该文字的元素(不区分大小写)。
    注意:按坐标判断是否在屏幕内,被弹窗遮住的元素也可能列出来,不确定时截图核对。
    """
    ensure_unlocked()
    els = _elements()
    if filter:
        els = elements.filter_elements(els, filter)
    lines = [elements.describe(e) for e in els[:limit]]
    more = f"\n……另有 {len(els) - limit} 个未列出,可用 filter 缩小范围" if len(els) > limit else ""
    return ("\n".join(lines) or "没有找到带文字的元素") + more


@mcp.tool(structured_output=False)
def iphone_tap(x: float, y: float) -> str:
    """点击屏幕坐标(点)。"""
    ensure_unlocked()
    try:
        wda.session("POST", "/wda/tap", {"x": x, "y": y})
        return f"已点击 ({x:g},{y:g})"
    except wda.WDAUnavailable:
        hid.run("universal-hid-service", "tap", *imaging.hid_norm(x, y, wda.screen()))
        return f"已点击 ({x:g},{y:g})(经 HID)"


@mcp.tool(structured_output=False)
def iphone_tap_element(text: str, index: int = 0) -> str:
    """按文字点击元素:先找标签/名字完全相同的,找不到再找包含该文字的。

    index: 匹配到多个时点第几个(从 0 开始,顺序同 iphone_list_elements)。
    """
    ensure_unlocked()
    matches = elements.match_elements(_elements(), text)
    if not matches:
        return f'没找到包含 "{text}" 的元素,先用 iphone_list_elements 或截图看看屏幕'
    if index >= len(matches):
        return f"只匹配到 {len(matches)} 个:\n" + "\n".join(elements.describe(e) for e in matches)
    e = matches[index]
    wda.session("POST", "/wda/tap", {"x": e["center"][0], "y": e["center"][1]})
    note = f"(共匹配 {len(matches)} 个,点的是第 {index} 个)" if len(matches) > 1 else ""
    return f"已点击 {elements.describe(e)}{note}"


@mcp.tool(structured_output=False)
def iphone_long_press(x: float, y: float, seconds: float = 1.0) -> str:
    """长按屏幕坐标(点)。"""
    ensure_unlocked()
    wda.session("POST", "/wda/touchAndHold", {"x": x, "y": y, "duration": seconds})
    return f"已长按 ({x:g},{y:g}) {seconds:g} 秒"


@mcp.tool(structured_output=False)
def iphone_swipe(from_x: float, from_y: float, to_x: float, to_y: float, seconds: float = 0.3) -> str:
    """从一点滑到另一点(点坐标)。向上滑看下面的内容:from_y 大、to_y 小。"""
    ensure_unlocked()
    try:
        wda.touch([(from_x, from_y, 0), (to_x, to_y, int(seconds * 1000))], pause_ms=50)
        return f"已滑动 ({from_x:g},{from_y:g}) → ({to_x:g},{to_y:g})"
    except wda.WDAUnavailable:
        s = wda.screen()
        hid.run("universal-hid-service", "drag", *imaging.hid_norm(from_x, from_y, s),
                *imaging.hid_norm(to_x, to_y, s), "--duration", seconds)
        return f"已滑动 ({from_x:g},{from_y:g}) → ({to_x:g},{to_y:g})(经 HID)"


@mcp.tool(structured_output=False)
def iphone_type_text(text: str, submit: bool = False) -> str:
    """在当前获得焦点的输入框里输入文字(支持中文)。需要先点中输入框。submit=True 时末尾按回车。"""
    ensure_unlocked()
    payload = text + ("\n" if submit else "")
    try:
        wda.session("POST", "/wda/keys", {"value": list(payload)}, timeout=120)
        return f"已输入 {len(text)} 个字符" + (",并按了回车" if submit else "")
    except wda.WDAUnavailable:
        if not payload.isascii():
            raise ToolError("WDA 不可用,HID 只能输入英文和符号") from None
        hid.run("universal-hid-service", "type", payload)
        return f"已输入 {len(text)} 个字符(经 HID)"


@mcp.tool(structured_output=False)
def iphone_press_button(button: str) -> str:
    """按硬件键:home(回主屏幕)、volume_up、volume_down、lock(锁屏;配置了密码时之后的操作会自动解锁)。"""
    if button == "lock":
        try:
            wda.session("POST", "/wda/lock")
        except wda.WDAUnavailable:
            hid.run("hid", "button", "lock")
        return "已锁屏"
    wda_name = {"home": "home", "volume_up": "volumeUp", "volume_down": "volumeDown"}.get(button)
    if not wda_name:
        raise ToolError("button 只能是 home / volume_up / volume_down / lock")
    ensure_unlocked()
    try:
        wda.session("POST", "/wda/pressButton", {"name": wda_name})
    except wda.WDAUnavailable:
        hid.run("hid", "button", button.replace("_", "-"))
    return f"已按 {button}"


@mcp.tool(structured_output=False)
def iphone_list_apps(include_system: bool = False) -> str:
    """列出已安装的 App(名字和 Bundle ID)。include_system=True 时列出系统 App。"""
    return "\n".join(f"{n}\t{b}" for n, b in _apps(include_system))


@mcp.tool(structured_output=False)
def iphone_launch_app(app: str) -> str:
    """启动 App 并切到前台。app 可以是 Bundle ID,也可以是显示名(如「设置」「微信」)。"""
    bid = _resolve_app(app)
    ensure_unlocked()
    wda.session("POST", "/wda/apps/launch", {"bundleId": bid}, timeout=60)
    # 冷启动后界面要过一会儿才响应点击,太早操作会被吞掉
    deadline = time.time() + 8
    while time.time() < deadline and wda.request("GET", "/wda/activeAppInfo")["value"].get("bundleId") != bid:
        time.sleep(0.5)
    time.sleep(1)
    return f"已启动 {bid}"


@mcp.tool(structured_output=False)
def iphone_terminate_app(app: str) -> str:
    """结束 App 进程。app 可以是 Bundle ID 或显示名。"""
    bid = _resolve_app(app)
    ensure_unlocked()
    wda.session("POST", "/wda/apps/terminate", {"bundleId": bid})
    return f"已结束 {bid}"


@mcp.tool(structured_output=False)
def iphone_open_url(url: str) -> str:
    """用系统默认方式打开链接或 URL Scheme(网页会在 Safari 打开)。"""
    ensure_unlocked()
    wda.session("POST", "/url", {"url": url}, timeout=60)
    return f"已打开 {url}"


def main():
    mcp.run()
