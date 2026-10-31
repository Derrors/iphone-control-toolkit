"""CoreDevice HID 后备路线(pymobiledevice3 命令行),WDA 不可用时用。

只在 iOS 27 及以上、开发者镜像已挂载时可用;锁屏时用不了。
"""
import re
import subprocess

from mcp.server.mcpserver.exceptions import ToolError

from . import config


def run(*args, timeout=90):
    try:
        r = subprocess.run([config.PMD3, "developer", "core-device", *map(str, args)],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ToolError(f"HID 命令超时({timeout} 秒)") from None
    if r.returncode:
        raise ToolError(f"HID 命令失败: {error_line(r.stderr or r.stdout) or r.returncode}")


def error_line(output):
    """从 pymobiledevice3 的输出里挑出真正的错误:跳过末尾的「Run again with -v」提示,去掉日志前缀。"""
    lines = [s for s in output.strip().splitlines() if "Run again with -v" not in s]
    if not lines:
        return ""
    # 形如「2026-10-31 17:21:12 host pymobiledevice3.__main__[113] ERROR Device is not connected.」
    return re.sub(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d \S+ \S+\[\d+\] [A-Z]+ ", "", lines[-1])
