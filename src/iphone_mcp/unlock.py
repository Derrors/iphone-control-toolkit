"""锁屏时用配置的数字密码自动解锁(可选功能,配置了 data/secrets/passcode 才启用)。

安全原则:每按一位都核对密码栏的已输入位数,对不上就停,输入不完整不算输错;
只有整串输完仍是锁屏才算输错一次,这时写停用标记并推送通知,之后不再自动尝试。
"""
import subprocess
import time

from mcp.server.mcpserver.exceptions import ToolError

from . import config, elements, wda


def _elements():
    xml = wda.request("GET", f"/source?format=xml&excluded_attributes={elements.SOURCE_EXCLUDED}",
                      timeout=60)["value"]
    return elements.parse_source(xml, wda.screen())


def _passcode_field():
    els = wda.session("POST", "/elements", {"using": "class name", "value": "XCUIElementTypeSecureTextField"})
    for e in els["value"]:
        eid = next(iter(e.values()))
        parsed = elements.parse_passcode_value(wda.session("GET", f"/element/{eid}/attribute/value")["value"])
        if parsed:
            return parsed
    return None


def _press(x, y):
    # 锁屏界面上 /wda/tap 每次要等约 2.9 秒,单个 W3C 手势约 0.7 秒;
    # 几位合成一个手势会按得太密漏键,所以一位一个手势
    wda.touch([(x, y, 0)], pause_ms=80)


def _tap_key(keys, digit, expect):
    """按一个数字键,等密码栏的已输入位数变成 expect;返回实际位数。"""
    _press(*keys[digit])
    deadline = time.time() + 1.5
    while True:
        f = _passcode_field()
        got = f[1] if f else -1
        if got >= expect or time.time() > deadline:
            return got
        time.sleep(0.15)


def _swipe_up_from_bottom():
    w, h = wda.screen()
    wda.touch([(w / 2, h - 8, 0), (w / 2, h * 0.45, 250)])


def _notify(title, body):
    subprocess.Popen([config.NOTIFY, title, body],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def ensure_unlocked():
    """锁屏时自动解锁;WDA 不可用时什么也不做,交给后面的调用去报错或退回 HID。

    锁屏界面上 Face ID 等动画一直在动,WDA 默认每个请求都等界面静止(最多 10 秒),
    等完密码键盘早就自动收起了。解锁期间把等待上限压到 1 秒(压到 0 会唤醒失败),结束后恢复。
    """
    try:
        if not wda.locked():
            return
    except (wda.WDAUnavailable, wda.WDAError):
        return
    saved = wda.session("GET", "/appium/settings")["value"]
    keep = {k: saved[k] for k in ("waitForIdleTimeout", "animationCoolOffTimeout") if k in saved}
    wda.session("POST", "/appium/settings", {"settings": {"waitForIdleTimeout": 1, "animationCoolOffTimeout": 0.2}})
    try:
        _unlock()
    finally:
        wda.session("POST", "/appium/settings", {"settings": keep})


def _unlock():
    if config.UNLOCK_GUARD.exists():
        raise ToolError("手机已锁屏;自动解锁之前失败过已停用。请人工解锁手机、核对密码配置,"
                        "再运行 `iphonectl unlock-reset`")
    try:
        code = config.PASSCODE_FILE.read_text().strip()
    except OSError:
        raise ToolError("手机已锁屏,且没有配置锁屏密码(`iphonectl passcode set`),需要人工解锁") from None
    if not code.isdigit():
        raise ToolError("自动解锁只支持纯数字锁屏密码")

    # 每轮:按 Home 唤醒(键盘已打开时会收起并清空半截输入)→ 上滑调出密码键盘 → 按第 1 位核对。
    # 键盘没显示时它的按键也常留在元素树里,不能据此判断键盘是否出来了;第 1 位没生效就是一位都没输,可以重来
    for _ in range(3):
        wda.session("POST", "/wda/pressButton", {"name": "home"})
        time.sleep(1.0)
        _swipe_up_from_bottom()
        time.sleep(1.5)
        if not wda.locked():
            return
        keys, field = elements.keypad(_elements()), _passcode_field()
        if not keys or not field or field[1]:
            continue
        if field[0] != len(code):
            raise ToolError(f"手机要求 {field[0]} 位密码,配置的是 {len(code)} 位,一位都没输")
        got = _tap_key(keys, code[0], 1)
        if got == 1:
            break
        if got > 1:
            raise ToolError("第 1 位输入异常,已停止(输入不完整不算输错)")
    else:
        raise ToolError("调不出锁屏密码键盘(一位都没输进去),请截图看看锁屏界面")

    for n, d in enumerate(code[1:-1], 2):
        if _tap_key(keys, d, n) != n:
            raise ToolError(f"第 {n} 位没按上,已停止(输入不完整不算输错),稍后再试")

    _press(*keys[code[-1]])
    deadline = time.time() + 5
    while time.time() < deadline:
        time.sleep(0.3)
        if not wda.locked():
            return
    config.UNLOCK_GUARD.write_text(time.strftime("%F %T") + " 整串密码输完仍是锁屏状态\n")
    _notify("iPhone 自动解锁失败,已停用",
            "整串密码输完手机仍锁着,可能密码配置不对。为免累计输错,自动解锁已停用。\n"
            "请人工解锁手机、核对密码(iphonectl passcode set),再运行 iphonectl unlock-reset。")
    raise ToolError("整串密码输完手机仍锁着,自动解锁已停用(防止输错次数累计),已推送通知")
