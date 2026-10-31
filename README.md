# iphone-control-toolkit

在 Linux 上控制一台真实的 iPhone,并通过 MCP 交给 Claude 等 AI 助手操作。
不需要 Mac,不需要付费开发者账号,不越狱。

*Drive a real iPhone from a Linux box (no Mac, no paid developer account, no jailbreak) and expose it to AI agents over MCP.*

> 这是一个**组装式**工具包:把 go-ios、pymobiledevice3、plumesign、WebDriverAgent 这些上游项目原样从锁定版本构建进一个容器,
> 由本项目的脚本和 MCP 服务串起来。各组件的版本和许可证见 [THIRD_PARTY.md](THIRD_PARTY.md)。

## 能做什么

- **看屏幕、点屏幕**:截图(可局部放大)、点击、滑动、长按、输入文字(支持中文)、Home/音量/锁屏键。
- **按控件操作**:读界面元素树,按名字点按钮;启动、结束 App,打开链接。
- **两条控制路线互为后备**:
  - **WebDriverAgent**(主):要用免费 Apple ID 签名,每 7 天自动重签。
  - **CoreDevice HID**(后备):iOS 27 起的苹果官方接口,免签名,只能截图和按坐标操作。
- **无人值守**:守护进程处理 USB 重插、手机重启、隧道断开、WDA 崩溃;描述文件快过期时自动重签。
  重签失败、手机离线、重启后需要输密码时,推送 Telegram/Bark 通知。
- **可选自动解锁**:手机可以正常锁屏,操作前用配置的密码解锁。每一位都核对,不会累计输错。

## 要求

| | |
|---|---|
| 宿主机 | Linux,x86_64(arm64 未测试),Docker 和 Docker Compose v2.24+ |
| 手机 | iOS 17 及以上;HID 后备路线需要 iOS 27。目前只在 iPhone 15 Pro Max / iOS 27.0.1 上实测过 |
| 账号 | 一个免费 Apple ID(建议专门注册一个,不用主账号) |
| 连接 | USB 数据线 |

## 快速开始

```bash
git clone <本仓库> && cd iphone-control-toolkit
bin/iphonectl setup
```

`setup` 一步步引导完成下面这些,每步都会先检测是否已经做过,可以重复运行:

1. 构建镜像、启动容器(首次构建要从源码编译 go-ios 和 plumesign,约 5~10 分钟)
2. 配对:手机上点「信任」
3. 打开开发者模式:手机会重启一次
4. 挂载开发者镜像
5. 登录 Apple ID:密码和验证码只在你的终端里输入
6. 把手机注册到 Apple ID 的设备列表
7. 签名 WebDriverAgent 并安装到手机
8. 在手机上信任开发者,等 WDA 就绪

完成后把 MCP 服务注册到 Claude Code:

```bash
bin/iphonectl mcp install     # 等同于 claude mcp add iphone -s user -- docker exec -i iphone-control-toolkit /opt/ictl/mcp-server.sh
```

新开的 Claude Code 会话里就能用 `iphone_*` 工具了。

## 日常命令

```bash
bin/iphonectl status          # 容器状态和最近的日志
bin/iphonectl doctor          # 逐层诊断,每项失败都给出修复办法
bin/iphonectl logs wda -f     # 看日志
bin/iphonectl resign --force  # 立即重签
bin/iphonectl login           # Apple ID 登录过期时重新登录
bin/iphonectl passcode set    # 启用自动解锁
bin/iphonectl help
```

## MCP 工具

| 工具 | 说明 |
|---|---|
| `iphone_status` | 连接状态、是否锁屏、前台 App |
| `iphone_screenshot` | 截图,缩放到点坐标;传 `x/y/width/height` 放大局部 |
| `iphone_list_elements` | 带文字的界面元素和中心点坐标 |
| `iphone_tap` / `iphone_tap_element` | 按坐标或按名字点击 |
| `iphone_swipe` / `iphone_long_press` | 滑动、长按 |
| `iphone_type_text` | 输入文字 |
| `iphone_press_button` | home、volume_up、volume_down、lock |
| `iphone_list_apps` / `iphone_launch_app` / `iphone_terminate_app` | App 管理,可以用显示名 |
| `iphone_open_url` | 打开链接或 URL Scheme |

游戏、地图、视频这类用引擎自己绘制的界面读不到元素树,只能看截图按坐标操作。

## 配置

复制 `.env.example` 为 `.env`(`setup` 会自动复制)。所有项都有默认值,常用的是:

- `HTTP_PROXY` / `HTTPS_PROXY`:访问苹果和 GitHub 需要代理时填。
- `TG_BOT_TOKEN` / `TG_CHAT_ID`、`BARK_SERVER` / `BARK_KEY`:通知。
- `DATA_DIR`:数据目录,默认 `./data`。

`data/` 里有配对记录、Apple ID 登录状态、开发私钥和锁屏密码:**请备份,不要提交,不要分享**。

## 文档

- [架构](docs/architecture.md):组件、两条控制路线、守护和重签流程、数据目录
- [故障排查](docs/troubleshooting.md):已知的坑和对应现象
- [安全](docs/security.md):风险和默认的保护措施
- [开发](docs/development.md):测试、升级上游版本

## 限制

- 一台宿主机同时只控制一部手机,也不要让两个实例同时连同一部手机。
- 免费 Apple ID 的描述文件 7 天过期,靠自动重签续期;Apple ID 登录过期后要人工重新登录。
- 手机重启后,首次启用 UI 自动化要在手机上输一次锁屏密码(iOS 的安全机制)。
- 读元素树按坐标判断是否在屏幕内,被弹窗挡住的元素也可能列出来。

## 许可证

本项目代码:MIT。镜像中包含 GPL-3.0 等许可证的上游组件,见 [THIRD_PARTY.md](THIRD_PARTY.md)。
