"""运行时配置,全部来自环境变量,默认值对应容器内的目录布局。"""
import json
import os
from pathlib import Path

DATA = Path(os.environ.get("ICTL_DATA", "/data"))
WDA_URL = f"http://127.0.0.1:{os.environ.get('WDA_PORT', '8100')}"
PMD3 = os.environ.get("ICTL_PMD3", "/opt/pmd3/bin/pymobiledevice3")
IOS = os.environ.get("ICTL_IOS", "ios")
NOTIFY = os.environ.get("ICTL_NOTIFY", "/opt/ictl/notify.sh")

PASSCODE_FILE = DATA / "secrets" / "passcode"
# 自动解锁输错一次就写这个标记并停用:iOS 连续输错会越锁越久,开了「抹掉数据」的话 10 次会清空手机
UNLOCK_GUARD = DATA / "logs" / "UNLOCK-DISABLED"
# WDA 可用时记下屏幕尺寸,WDA 不可用、走 HID 换算坐标时用
SCREEN_CACHE = DATA / "state" / "screen.json"


def fallback_screen():
    """WDA 不可用时的屏幕尺寸(点):先用环境变量,再用上次缓存;都没有返回 None。"""
    w, h = os.environ.get("SCREEN_W"), os.environ.get("SCREEN_H")
    if w and h:
        return int(w), int(h)
    try:
        d = json.loads(SCREEN_CACHE.read_text())
        return int(d["width"]), int(d["height"])
    except (OSError, ValueError, KeyError):
        return None


def save_screen(size):
    try:
        SCREEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
        SCREEN_CACHE.write_text(json.dumps({"width": size[0], "height": size[1]}))
    except OSError:
        pass
