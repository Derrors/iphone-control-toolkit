"""App 列表解析和按名字查 Bundle ID。纯函数,不访问设备。"""
import json


def parse_apps(text):
    """解析 `ios apps` 的 JSON 输出,返回按名字排序的 [(显示名, Bundle ID)]。

    带 hidden 标记的是系统后台服务(比如有 5 个也叫「设置」),去掉,免得按名字匹配到它们。
    """
    data = json.loads(text or "[]")
    return sorted(
        ((a.get("CFBundleDisplayName") or a.get("CFBundleName") or "", a["CFBundleIdentifier"])
         for a in data if "hidden" not in (a.get("SBAppTags") or [])),
        key=lambda t: t[0])


def resolve(app, sources):
    """把显示名或 Bundle ID 解析成 Bundle ID;找不到返回 None。

    sources 是按优先级排列的零参函数,各返回一个 App 列表(比如先用户 App 再系统 App)。
    列系统 App 要好几秒,所以只在前面的列表里找不到时才去取。
    先在所有列表里找名字完全相同的,再找包含该文字的。
    """
    if "." in app and " " not in app:
        return app
    fetched = []

    def lists():
        for i, source in enumerate(sources):
            if i == len(fetched):
                fetched.append(list(source()))
            yield fetched[i]

    for apps in lists():
        for name, bid in apps:
            if name == app:
                return bid
    for apps in lists():
        for name, bid in apps:
            if app.lower() in name.lower():
                return bid
    return None
