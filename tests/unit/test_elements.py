from pathlib import Path

import pytest

from iphone_mcp import elements

SCREEN = (430, 932)
HOME = (Path(__file__).parent / "fixtures" / "home.xml").read_text()


@pytest.fixture
def home():
    return elements.parse_source(HOME, SCREEN)


def labels(els):
    return [e["label"] or e["name"] for e in els]


def test_full_screen_containers_are_dropped(home):
    assert "Home screen icons" not in labels(home)
    assert all(e["type"] not in ("Application", "Window") for e in home)


def test_child_repeating_parent_label_and_rect_is_deduped(home):
    assert labels(home).count("设置") == 1
    assert home[labels(home).index("设置")]["type"] == "Icon"


def test_offscreen_page_and_degenerate_elements_are_dropped(home):
    assert "第二页的 App" not in labels(home)
    assert "零宽" not in labels(home)


def test_unlabeled_elements_are_dropped(home):
    assert all(e["label"] or e["name"] or e["value"] for e in home)


def test_center_is_clipped_to_visible_part(home):
    e = next(e for e in home if e["label"] == "被顶出屏幕一半")
    assert e["center"] == (150, 10)  # y 只算屏幕内的 0..20
    s = next(e for e in home if e["label"].startswith("垂直滚动条"))
    assert s["center"][0] == 421  # x 412..430


def test_type_prefix_is_removed(home):
    assert {e["type"] for e in home} >= {"Icon", "Button", "StaticText"}


def test_describe_shows_id_and_value():
    btn = elements.parse_source(HOME, SCREEN)
    d = {e["label"]: elements.describe(e) for e in btn}
    assert d["显示与亮度"] == 'Button "显示与亮度" id="com.apple.settings.displayAndBrightness" @(215,676) 390x53'
    assert 'value="1个新项目"' in d["设置"]


def test_match_prefers_exact_over_substring(home):
    assert labels(elements.match_elements(home, "时钟")) == ["时钟"]
    assert labels(elements.match_elements(home, "亮度")) == ["显示与亮度"]
    assert elements.match_elements(home, "不存在") == []


def test_match_by_name_id(home):
    assert labels(elements.match_elements(home, "com.apple.settings.displayAndBrightness")) == ["显示与亮度"]


def test_filter_is_case_insensitive_and_checks_value(home):
    assert labels(elements.filter_elements(home, "新项目")) == ["设置"]


def _key(label, x, y, type_="Key"):
    return {"type": type_, "label": label, "name": label, "value": "", "center": (x, y), "size": (80, 80)}


def test_keypad_needs_all_ten_digits():
    keys = [_key(str(d), d * 10, 100) for d in range(10)]
    pad = elements.keypad(keys)
    assert pad["0"] == (0, 100) and pad["9"] == (90, 100)
    assert elements.keypad(keys[:9]) is None


def test_keypad_accepts_letters_after_digit_but_not_multi_digit_labels():
    keys = [_key(f"{d} ABC", d, 0, "Button") for d in range(10)]
    assert elements.keypad(keys) is not None
    keys = [_key(str(d), d, 0) for d in range(9)] + [_key("10", 0, 0)]
    assert elements.keypad(keys) is None


def test_keypad_ignores_non_key_types():
    keys = [_key(str(d), d, 0, "StaticText") for d in range(10)]
    assert elements.keypad(keys) is None


@pytest.mark.parametrize("value,expected", [
    ("共6位数，已输入0位", (6, 0)),
    ("共6位数，已输入2位", (6, 2)),
    ("6-digit passcode, 3 entered", (6, 3)),
    ("共4位数", None),
    ("", None),
    (None, None),
])
def test_parse_passcode_value(value, expected):
    assert elements.parse_passcode_value(value) == expected
