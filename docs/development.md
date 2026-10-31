# 开发

## 目录

```
bin/iphonectl          宿主机命令行
container/             容器内脚本:入口、守护、重签、诊断、通知
src/iphone_mcp/        MCP 服务
  elements.py          元素树解析(纯函数)
  imaging.py           截图缩放、区域放大、HID 坐标换算(纯函数)
  apps.py              App 列表解析、按名字查 Bundle ID(纯函数)
  wda.py               WDA HTTP 客户端
  hid.py               HID 后备路线
  unlock.py            自动解锁
  server.py            MCP 工具定义
docker/                Dockerfile 和 Python 依赖锁定
tests/unit/            不碰设备的单元测试
tests/device/          真机回归测试
```

## 测试

```bash
pip install pytest pillow ruff
pytest -q                     # 单元测试
ruff check src tests
shellcheck -x container/*.sh bin/iphonectl
```

真机回归测试会实际操作手机(只做无害操作:回主屏幕、打开时钟切页、搜索框输入文字):

```bash
bin/iphonectl test-device                                   # 默认步骤
bin/iphonectl test-device '[["iphone_status", {}], ["iphone_screenshot", {}]]'
```

截图保存在 `data/test-shots/`。

改了 `src/` 或 `container/` 后需要重建镜像:`bin/iphonectl up`(会自动构建)。

## 升级上游版本

所有版本都锁在 `docker/Dockerfile` 的 `ARG` 和 `docker/constraints-*.txt` 里。升级流程:

1. 改对应的 `ARG`(go-ios 用完整提交号;Impactor 同时改 tag 和对应提交号;WDA 同时改版本和 sha256)。
2. Python 依赖:在新镜像里 `pip freeze` 重新生成 constraints。
3. 重建镜像,跑单元测试和真机回归测试,至少覆盖:签名安装、WDA 启动、截图、HID 点击、自动解锁。
4. 同步更新 `THIRD_PARTY.md`。

注意过的不兼容:mcp 2.x 把 `FastMCP` 改名为 `MCPServer`,`CallToolResult.isError` 改为 `is_error`;
go-ios 的 `sign app`、`ui` 等命令只在 main 分支,没进正式版,所以锁的是提交号而不是版本号。

## WDA 的 Bundle ID

plumesign 申请描述文件时会把 WDA 的 Bundle ID 改成 `com.facebook.WebDriverAgentRunner.xctrunner.<团队 ID>`。
这个值在首次签名后写入 `data/state/wda-bundle`,supervisor 和诊断都从这里读。
