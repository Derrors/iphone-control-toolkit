import json

from iphone_mcp import apps

SYSTEM = json.dumps([
    {"CFBundleDisplayName": "设置", "CFBundleIdentifier": "com.apple.NewDeviceSetupUIService", "SBAppTags": ["hidden"]},
    {"CFBundleDisplayName": "设置", "CFBundleIdentifier": "com.apple.Preferences"},
    {"CFBundleDisplayName": "设置", "CFBundleIdentifier": "com.apple.CarPlaySettings", "SBAppTags": ["hidden"]},
    {"CFBundleName": "时钟", "CFBundleIdentifier": "com.apple.mobiletimer"},
    {"CFBundleDisplayName": "Safari浏览器", "CFBundleIdentifier": "com.apple.mobilesafari"},
])
USER = json.dumps([
    {"CFBundleDisplayName": "开心消消乐", "CFBundleIdentifier": "com.example.game"},
    {"CFBundleDisplayName": "设置助手", "CFBundleIdentifier": "com.example.settingshelper"},
])


def test_hidden_system_services_are_skipped():
    parsed = apps.parse_apps(SYSTEM)
    assert ("设置", "com.apple.Preferences") in parsed
    assert all(bid != "com.apple.NewDeviceSetupUIService" for _, bid in parsed)


def test_bundle_name_is_used_when_display_name_missing():
    assert ("时钟", "com.apple.mobiletimer") in apps.parse_apps(SYSTEM)


def test_empty_output():
    assert apps.parse_apps("") == []


def sources(calls):
    def user():
        calls.append("user")
        return apps.parse_apps(USER)

    def system():
        calls.append("system")
        return apps.parse_apps(SYSTEM)

    return [user, system]


def test_exact_name_in_system_beats_substring_in_user():
    # 「设置」完全匹配系统的设置,不能被用户 App「设置助手」的包含匹配抢走
    assert apps.resolve("设置", sources([])) == "com.apple.Preferences"


def test_system_list_is_fetched_only_when_needed():
    calls = []
    assert apps.resolve("开心消消乐", sources(calls)) == "com.example.game"
    assert calls == ["user"]


def test_substring_match_and_case_insensitivity():
    assert apps.resolve("safari", sources([])) == "com.apple.mobilesafari"
    assert apps.resolve("消消", sources([])) == "com.example.game"


def test_bundle_id_passes_through_without_listing():
    calls = []
    assert apps.resolve("com.apple.Preferences", sources(calls)) == "com.apple.Preferences"
    assert calls == []


def test_unknown_returns_none():
    assert apps.resolve("不存在的 App", sources([])) is None
