"""WDA 元素树解析。纯函数,不访问设备。"""
import re
import xml.etree.ElementTree as ET

# 不让 WDA 算可见性等属性:完整树要 7~8 秒,去掉后约 0.3 秒;可见性改按坐标判断
SOURCE_EXCLUDED = (
    "visible,accessible,focused,enabled,selected,index,traits,"
    "placeholderValue,hittable,customActions,nativeFrame"
)


def parse_source(xml, screen):
    """把 /source?format=xml 的结果解析成带文字、在屏幕内的元素列表。

    screen 是屏幕尺寸(点)。不在屏幕内的(比如主屏幕的其他页)、铺满全屏的容器、
    和父元素重复同一标签与位置的子元素都去掉。center 取元素在屏幕内那部分的中心。
    """
    sw, sh = screen
    root = ET.fromstring(xml.encode() if isinstance(xml, str) else xml)
    seen, out = set(), []
    for el in root.iter():
        a = el.attrib
        label, name, value = ((a.get(k) or "").strip() for k in ("label", "name", "value"))
        text = label or name or value
        if not text:
            continue
        x, y, w, h = (float(a.get(k, 0)) for k in ("x", "y", "width", "height"))
        if w <= 0 or h <= 0 or x >= sw or y >= sh or x + w <= 0 or y + h <= 0:
            continue
        if w >= sw and h >= sh:  # Application/Window 之类的容器,没有定位价值
            continue
        key = (text, round(x), round(y), round(w), round(h))
        if key in seen:
            continue
        seen.add(key)
        vx1, vy1, vx2, vy2 = max(x, 0), max(y, 0), min(x + w, sw), min(y + h, sh)
        out.append({
            "type": a.get("type", el.tag).removeprefix("XCUIElementType"),
            "label": label, "name": name, "value": value,
            "center": (round((vx1 + vx2) / 2), round((vy1 + vy2) / 2)),
            "size": (round(w), round(h)),
        })
    return out


def describe(e):
    s = f'{e["type"]} "{e["label"] or e["name"] or e["value"]}"'
    if e["name"] and e["label"] and e["name"] != e["label"]:
        s += f' id="{e["name"]}"'
    if e["value"] and e["value"] not in (e["label"], e["name"]):
        s += f' value="{e["value"][:60]}"'
    return s + f' @({e["center"][0]},{e["center"][1]}) {e["size"][0]}x{e["size"][1]}'


def _haystack(e):
    return f'{e["label"]} {e["name"]} {e["value"]}'.lower()


def filter_elements(elements, text):
    """标签/名字/值里包含 text 的元素(不区分大小写)。"""
    t = text.lower()
    return [e for e in elements if t in _haystack(e)]


def match_elements(elements, text):
    """按文字找元素:先找标签或名字完全相同的,没有再找包含该文字的。"""
    exact = [e for e in elements if text in (e["label"], e["name"])]
    return exact or filter_elements(elements, text)


def keypad(elements):
    """锁屏密码键盘上 0~9 各键的中心点;没找齐 10 个键返回 None。

    注意:键盘没显示时,这些 Key 元素常常还留在树里,所以「找到了」不代表键盘在屏幕上,
    调用方要按键后再核对密码栏的已输入位数。
    """
    keys = {}
    for e in elements:
        if e["type"] not in ("Button", "Key"):
            continue
        for t in (e["label"], e["name"]):
            t = t.strip()
            # 键的标签可能是 "2" 或 "2 ABC"
            if t[:1].isdigit() and (len(t) == 1 or not t[1].isdigit()):
                keys.setdefault(t[0], e["center"])
                break
    return keys if len(keys) == 10 else None


def parse_passcode_value(value):
    """锁屏密码栏的值形如「共6位数，已输入2位」,返回 (总位数, 已输入位数);认不出返回 None。"""
    nums = [int(n) for n in re.findall(r"\d+", value or "")]
    return (nums[0], nums[1]) if len(nums) == 2 else None
