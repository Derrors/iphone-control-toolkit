# iphone-control-toolkit

[![CI](https://github.com/Derrors/iphone-control-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/Derrors/iphone-control-toolkit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

在 Linux 上控制一台真实的 iPhone,并通过 MCP 交给 Claude 等 AI 助手操作。
不需要 Mac,不需要付费开发者账号,不越狱。

*Drive a real iPhone from a Linux box — no Mac, no paid developer account, no jailbreak — and expose it to AI agents over MCP. See [English summary](#english-summary).*

> 这是一个**组装式**工具包:把 go-ios、pymobiledevice3、plumesign、WebDriverAgent 这些上游项目原样从锁定的版本构建进一个容器,
> 由本项目的守护脚本和 MCP 服务串起来。各组件的版本和许可证见 [THIRD_PARTY.md](THIRD_PARTY.md)。

## 能做什么

- **看屏幕、点屏幕**:截图(可局部放大看小字)、点击、滑动、长按、输入文字(支持中文)、Home/音量/锁屏键。
- **按控件操作**:读界面元素树,按名字点按钮;启动、结束 App,打开链接。
- **两条控制路线互为后备**:
  - **WebDriverAgent**(主):用免费 Apple ID 签名,每 7 天自动重签。
  - **CoreDevice HID**(后备):iOS 27 起的苹果官方接口,免签名,只能截图和按坐标操作。WDA 挂了时自动切过去。
- **无人值守**:守护进程处理 USB 重插、手机重启、隧道断开、WDA 崩溃;描述文件快过期时自动重签。
  重签失败、手机离线、重启后需要输密码时,推送 Telegram / Bark 通知。
- **可选自动解锁**:手机可以正常锁屏,操作前用配置的数字密码解锁。逐位核对输入,
  密码配置错误时最多输错一次就自动停用,不会累计错误次数。

## 状态

早期版本,目前只在 **iPhone 15 Pro Max / iOS 27.0.1**、x86_64 Debian 宿主机上实测过。

| 已在真机验证 | 尚未在本项目中端到端验证 |
|---|---|
| 守护与自动恢复(USB 重插、usbmuxd 自愈、隧道、WDA 拉起)<br>手机重启后的密码框检测与通知<br>全部 13 个 MCP 工具、HID 后备路线、锁屏自动解锁<br>免费 Apple ID 重签(约 10 秒)和重签后 WDA 自动恢复 | `iphonectl setup` 从零开始的完整首次安装<br>(各步骤的底层命令都实测过,但没有在全新环境里串起来跑)<br>iOS 17~26、其他机型、arm64 宿主机 |

遇到问题欢迎提 issue,附上 `iphonectl doctor` 的输出(注意先去掉 UDID)。

## 要求

| | |
|---|---|
| 宿主机 | Linux,Docker 和 Docker Compose v2.24+。x86_64 已测试,arm64 未测试 |
| 手机 | iOS 17 及以上;HID 后备路线需要 iOS 27 |
| 账号 | 一个免费 Apple ID(建议专门注册一个,不要用主账号) |
| 连接 | 能传数据的 USB 线(只能充电的线识别不到手机) |

## 快速开始

```bash
git clone https://github.com/Derrors/iphone-control-toolkit.git
cd iphone-control-toolkit
bin/iphonectl setup
```

`setup` 一步步引导完成下面这些。每一步都会先检测是否已经做过,中途断了重新运行即可:

1. 构建镜像、启动容器。首次构建要从源码编译 go-ios 和 plumesign,约 5~10 分钟
2. 配对:手机上点「信任」并输入锁屏密码
3. 打开开发者模式:手机会重启一次
4. 挂载开发者镜像
5. 登录 Apple ID:密码和双重认证验证码只在你自己的终端里输入
6. 把手机注册到这个 Apple ID 的开发者设备列表
7. 签名 WebDriverAgent 并安装到手机
8. 在手机的 设置 → 通用 → VPN 与设备管理 里信任开发者,等 WDA 就绪

完成后注册到 Claude Code:

```bash
bin/iphonectl mcp install
```

新开一个 Claude Code 会话,就可以这样用:

> 打开「时钟」,切到秒表页,截图给我看
>
> 在 App Store 里搜索「备忘录」,告诉我第一个结果的评分

想在任意目录使用 `iphonectl`:`ln -s "$PWD/bin/iphonectl" ~/.local/bin/iphonectl`。

### 接入其他 MCP 客户端

MCP 服务走 stdio,通过 `docker exec` 启动,不开放网络端口:

```json
{
  "mcpServers": {
    "iphone": {
      "command": "docker",
      "args": ["exec", "-i", "iphone-control-toolkit", "/opt/ictl/mcp-server.sh"]
    }
  }
}
```

## 日常命令

```bash
bin/iphonectl status          # 容器状态和最近的守护日志
bin/iphonectl doctor          # 逐层诊断,每项失败都给出修复办法
bin/iphonectl logs wda -f     # 看日志:supervisor / wda / tunnel / resign / notify …
bin/iphonectl resign --force  # 立即重签
bin/iphonectl login           # Apple ID 登录过期时重新登录
bin/iphonectl notify-test     # 测试通知
bin/iphonectl passcode set    # 启用自动解锁
bin/iphonectl help
```

## MCP 工具

| 工具 | 说明 |
|---|---|
| `iphone_status` | 连接状态、是否锁屏、前台 App、屏幕尺寸 |
| `iphone_screenshot` | 截图,已缩放到点坐标;传 `x/y/width/height` 放大局部 |
| `iphone_list_elements` | 带文字的界面元素和中心点坐标,可按文字筛选 |
| `iphone_tap` / `iphone_tap_element` | 按坐标或按名字点击 |
| `iphone_swipe` / `iphone_long_press` | 滑动、长按 |
| `iphone_type_text` | 输入文字(WDA 可输中文;HID 后备只支持英文) |
| `iphone_press_button` | home、volume_up、volume_down、lock |
| `iphone_list_apps` / `iphone_launch_app` / `iphone_terminate_app` | App 管理,可以直接写显示名,如「设置」 |
| `iphone_open_url` | 打开链接或 URL Scheme |

截图的像素坐标就是点击坐标,AI 看图后可以直接点。
游戏、地图、视频这类由引擎自己绘制的界面读不到元素树,只能看截图按坐标操作。

## 配置

`setup` 会把 `.env.example` 复制为 `.env`。所有项都有默认值,常用的是:

- `HTTP_PROXY` / `HTTPS_PROXY`:访问苹果和 GitHub 需要代理时填。
- `TG_BOT_TOKEN` / `TG_CHAT_ID`、`BARK_SERVER` / `BARK_KEY`:通知。
- `PUID` / `PGID`:数据目录归属的宿主机用户,填 `id -u` / `id -g` 的结果。
- `DATA_DIR`:数据目录,默认 `./data`。

`data/` 里有配对记录、Apple ID 登录状态、开发私钥和锁屏密码:**请备份,不要提交,不要分享**。

## 手机设置建议

手机会长期插着电、经常亮屏:

- 设置 → 电池 → 充电,选「80% 上限」,减少电池损耗。
- 亮度调低、用深色壁纸,降低 OLED 烧屏风险。
- 没启用自动解锁时,「自动锁定」要设为「永不」,否则锁屏后只能人工解锁。

## 卸载

```bash
bin/iphonectl down
docker rmi iphone-control-toolkit:local
rm -rf data .env            # 会删掉配对记录、登录状态和私钥
claude mcp remove iphone -s user
```

然后在手机上关闭开发者模式,删除 WebDriverAgentRunner;在 Apple ID 的开发者设备列表里移除这台手机。

## 文档

- [架构](docs/architecture.md):组件、两条控制路线、守护和重签流程、数据目录
- [故障排查](docs/troubleshooting.md):已知的坑和对应现象
- [安全](docs/security.md):风险和默认的保护措施
- [开发](docs/development.md):测试、升级上游版本

## 限制

- 一台宿主机同时只控制一部手机;不要让两个实例同时连同一部手机。
- 免费 Apple ID 的描述文件 7 天过期,靠自动重签续期;Apple ID 登录过期后要人工重新登录。
- 手机重启后,首次启用 UI 自动化要在手机上输一次锁屏密码(iOS 的安全机制,无法绕过)。
- 读元素树按坐标判断元素是否在屏幕内,被弹窗挡住的元素也可能列出来。

## 免责声明

本项目与 Apple 无关。请只用于你自己拥有的设备,遵守 Apple 开发者协议和当地法律。
AI 操作手机可能误触付款、删除、发送消息等操作,请保持 Claude Code 的工具调用确认,并阅读 [安全说明](docs/security.md)。

## 许可证

本项目代码采用 MIT 许可证。镜像中包含 GPL-3.0 等许可证的上游组件,见 [THIRD_PARTY.md](THIRD_PARTY.md)。

## English summary

**iphone-control-toolkit** lets an AI agent (Claude Code or any MCP client) operate a real iPhone attached by USB
to a Linux host. It bundles go-ios, pymobiledevice3, plumesign and WebDriverAgent — built unmodified from pinned
sources — into one container, plus:

- an MCP server with 13 tools (screenshot with zoom, element tree, tap by name or coordinates, swipe, text input
  including CJK, hardware buttons, app launch/terminate, open URL);
- WebDriverAgent as the primary channel and CoreDevice HID (iOS 27+, no signing needed) as automatic fallback;
- a supervisor that recovers from replugging, phone reboots, tunnel drops and WDA crashes, re-signs WDA with a
  free Apple ID before the 7-day profile expires, and sends Telegram/Bark alerts;
- optional auto-unlock with per-digit verification that disables itself after a single wrong attempt.

Quick start: `bin/iphonectl setup`, then `bin/iphonectl mcp install`. Docs are in Chinese for now; issues and PRs in
English are welcome.
