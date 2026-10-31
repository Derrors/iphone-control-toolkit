"""真机回归测试:按 stdio 协议启动 MCP 服务,依次调用工具并打印结果。

在容器里运行(iphonectl test-device 会处理):
    iphonectl test-device                      # 跑默认步骤
    iphonectl test-device '[["iphone_status", {}]]'
截图存到容器的 /data/test-shots/(宿主机 data/test-shots/)。
默认步骤只做无害操作:回主屏幕、打开时钟切页、下拉搜索输入中文,最后回主屏幕。
"""
import asyncio
import base64
import json
import os
import sys
import time

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

STEPS = [
    ("iphone_status", {}),
    ("iphone_tap_element", {"text": "不存在的按钮xyz"}),
    ("iphone_press_button", {"button": "home"}),
    ("iphone_launch_app", {"app": "时钟"}),
    ("iphone_list_elements", {"limit": 12}),
    ("iphone_tap_element", {"text": "秒表"}),
    ("iphone_screenshot", {}),
    ("iphone_screenshot", {"x": 0, "y": 0, "width": 430, "height": 60}),
    ("iphone_press_button", {"button": "home"}),
    ("iphone_swipe", {"from_x": 215, "from_y": 400, "to_x": 215, "to_y": 700}),
    ("iphone_type_text", {"text": "设置"}),
    ("iphone_screenshot", {}),
    ("iphone_press_button", {"button": "home"}),
]
SHOTS = "/data/test-shots"


async def main():
    steps = [tuple(x) for x in json.loads(sys.argv[1])] if len(sys.argv) > 1 else STEPS
    os.makedirs(SHOTS, exist_ok=True)
    params = StdioServerParameters(command=os.environ.get("MCP_CMD", "/opt/ictl/mcp-server.sh"))
    failed = 0
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        n = 0
        for name, args in steps:
            t = time.time()
            res = await s.call_tool(name, args)
            await asyncio.sleep(1.0)
            out = []
            for c in res.content:
                if c.type == "image":
                    n += 1
                    with open(f"{SHOTS}/shot{n}.jpg", "wb") as f:
                        f.write(base64.b64decode(c.data))
                    out.append(f"<image {SHOTS}/shot{n}.jpg>")
                else:
                    out.append(c.text)
            failed += bool(res.is_error)
            flag = "ERROR " if res.is_error else ""
            print(f"--- {name} {args} {time.time() - t:.1f}s {flag}\n" + "\n".join(out)[:900])
    sys.exit(1 if failed else 0)


asyncio.run(main())
