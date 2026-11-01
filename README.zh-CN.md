# iphone-control-toolkit

[![CI](https://github.com/Derrors/iphone-control-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/Derrors/iphone-control-toolkit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[English](README.md) | 简体中文

让 AI 助手操作一台插在 Linux 机器上的真实 iPhone。
不需要 Mac，不需要付费开发者账号，不越狱。

```
Claude Code / 任意 MCP 客户端
        │  MCP（stdio，经 docker exec）
        ▼
┌──────────── Linux 上的 Docker 容器 ─────────────┐
│  MCP 服务 ── WebDriverAgent（主路线）            │
│           └─ CoreDevice HID（后备，iOS 27+）     │
│  守护进程：断线重连、自动重启、自动重签          │
└──────────────────────┬──────────────────────────┘
                       │ USB
                    iPhone
```

## 功能

- **看屏幕、点屏幕**：截图（可放大局部）、点击、滑动、长按、输入文字（支持中文）、硬件按键。
- **按控件操作**：读取界面元素树，按名字点按钮；启动、结束 App，打开链接。
- **两条控制路线**：平时由 WebDriverAgent 完成；它不可用时，截图、点击、滑动、按键自动改走苹果的 CoreDevice HID 服务（iOS 27+，免签名）。
- **无人值守**：USB 重插、手机重启、隧道断开、WebDriverAgent 崩溃后都能自动恢复；免费 Apple ID 的描述文件 7 天到期前自动重签。
- **通知**：重签失败、手机离线、重启后需要输入密码时，推送 Telegram 或 Bark。
- **可选自动解锁**：手机可以正常锁屏，操作前自动输入数字密码。每一位都会核对；密码配置错误时，输错一次就停用自动解锁。

## 要求

| | |
|---|---|
| 宿主机 | Linux，Docker 及 Compose v2.24+（已在 x86_64 上测试） |
| 手机 | iOS 17+；HID 后备路线需要 iOS 27+ |
| 账号 | 一个免费 Apple ID（建议专门注册一个，不要用主账号） |
| 数据线 | 能传数据的 USB 线，只能充电的线识别不到手机 |

## 快速开始

```bash
git clone https://github.com/Derrors/iphone-control-toolkit.git
cd iphone-control-toolkit
bin/iphonectl setup          # 引导式安装，可重复运行
bin/iphonectl mcp install    # 注册到 Claude Code
```

`setup` 会逐步引导，已经完成的步骤自动跳过：

1. 构建镜像、启动容器（首次构建要从源码编译，约 5～10 分钟）。
2. 配对：在手机上点「信任」。
3. 打开开发者模式（手机会重启一次）。
4. 挂载开发者镜像。
5. 登录 Apple ID（密码和双重认证验证码只在你自己的终端里输入）。
6. 注册手机，签名并安装 WebDriverAgent。
7. 在手机的 **设置 → 通用 → VPN 与设备管理** 里信任开发者。

然后新开一个 Claude Code 会话，比如这样说：

> 打开「时钟」，切到秒表页，截图给我看。

**其他 MCP 客户端**：服务通过 `docker exec` 走 stdio，不开放网络端口：

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

## 常用命令

| 命令 | 作用 |
|---|---|
| `iphonectl status` | 容器状态和最近的守护日志 |
| `iphonectl doctor` | 逐层诊断，每项失败都给出修复办法 |
| `iphonectl logs [名字] [-f]` | 看日志：`supervisor`、`wda`、`tunnel`、`resign`、`notify` 等 |
| `iphonectl resign [--force]` | 快过期时重签 WebDriverAgent；`--force` 立即重签 |
| `iphonectl login` | Apple ID 登录过期时重新登录 |
| `iphonectl notify-test` | 发一条测试通知 |
| `iphonectl passcode set\|clear` | 开启或关闭自动解锁 |
| `iphonectl help` | 全部命令 |

## MCP 工具

| 工具 | 说明 |
|---|---|
| `iphone_status` | 连接状态、是否锁屏、前台 App、屏幕尺寸 |
| `iphone_screenshot` | 截图，已缩放到点坐标；传 `x/y/width/height` 放大局部 |
| `iphone_list_elements` | 带文字的界面元素及其中心坐标 |
| `iphone_tap` / `iphone_tap_element` | 按坐标或按名字点击 |
| `iphone_swipe` / `iphone_long_press` | 滑动、长按 |
| `iphone_type_text` | 在当前输入框里输入文字 |
| `iphone_press_button` | `home`、`volume_up`、`volume_down`、`lock` |
| `iphone_list_apps` / `iphone_launch_app` / `iphone_terminate_app` | 按名字或 Bundle ID 管理 App |
| `iphone_open_url` | 打开链接或 URL Scheme |

截图的像素坐标就是点击坐标，AI 看到哪里就能点哪里。
游戏、地图、视频播放器自己绘制界面，没有元素树，只能看截图按坐标操作。

## 配置

`setup` 会把 `.env.example` 复制为 `.env`。所有项都有默认值，最常改的是：

| 配置项 | 用途 |
|---|---|
| `HTTP_PROXY`、`HTTPS_PROXY` | 访问苹果和 GitHub 需要代理时填 |
| `TG_BOT_TOKEN`、`TG_CHAT_ID` | Telegram 通知 |
| `BARK_SERVER`、`BARK_KEY` | Bark 通知 |
| `PUID`、`PGID` | 数据目录归属的宿主机用户（`id -u`、`id -g`） |

所有状态都在 `data/` 里：配对记录、Apple ID 登录状态和签名私钥、证书、锁屏密码。**请备份，不要提交，不要分享。**

## 当前状态

早期版本，目前只在 **iPhone 15 Pro Max / iOS 27.0.1** 和 x86_64 Debian 宿主机上测试过。

- **已在真机验证**：重插和重启后的自动恢复、需要输密码时的提醒、全部 13 个 MCP 工具、HID 后备路线、自动解锁、重签。
- **尚未端到端验证**：从零开始完整跑一遍 `setup`（各步骤单独测过）、iOS 17～26、其他机型、arm64 宿主机。

遇到问题欢迎提 issue，请附上 `iphonectl doctor` 的输出（先去掉 UDID）。

## 限制

- 一台宿主机只控制一部手机，不要让两个实例同时连同一部手机。
- 免费 Apple ID 的描述文件 7 天过期。重签是自动的，但 Apple ID 登录过期后要运行 `iphonectl login`。
- 手机重启后，要在手机上输一次锁屏密码，才能启用 UI 自动化。这是 iOS 的要求。
- 可见性按坐标判断，被弹窗挡住的元素也可能被列出来。

## 文档

[架构](docs/architecture.md) · [故障排查](docs/troubleshooting.md) · [安全](docs/security.md) · [开发](docs/development.md)

## 安全与免责声明

这个工具能完全控制你的手机。WebDriverAgent 没有认证，所以只在 `127.0.0.1` 上开放；自动解锁默认关闭。详见 [docs/security.md](docs/security.md)。

本项目与 Apple 无关。请只用于你自己的设备，并遵守 Apple 开发者协议和当地法律。AI 可能会点到付款、删除、发送等按钮，请在 MCP 客户端里保持工具调用确认。

## 许可证

本项目代码采用 MIT 许可证。容器镜像还包含其他许可证（包括 GPL-3.0）的上游组件，见 [THIRD_PARTY.md](THIRD_PARTY.md)。
