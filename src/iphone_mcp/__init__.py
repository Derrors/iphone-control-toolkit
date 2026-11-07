"""通过 WebDriverAgent 和 CoreDevice HID 操作一台真实 iPhone 的 MCP 服务。

纯逻辑模块(elements、imaging、apps)不依赖 mcp,可以单独测试;
wda、hid、unlock、server 依赖 mcp SDK 和运行中的设备。
"""

__version__ = "0.2.0"
