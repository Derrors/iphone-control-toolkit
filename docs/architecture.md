# 架构

## 总览

```
┌─────────────── 宿主机(Linux)────────────────────────────────────────────┐
│  bin/iphonectl ── docker compose / docker exec                             │
│  iphonectl viewer (Tk) ── stream 127.0.0.1:9100, input 127.0.0.1:8100      │
│  Claude Code ── docker exec -i <容器> /opt/ictl/mcp-server.sh (stdio)      │
│                                                                            │
│  ┌──────────── 容器(privileged,host 网络,不对外开放端口)──────────────┐  │
│  │ entrypoint.sh → supervisor.sh(每 10 秒巡检)                         │  │
│  │   ├─ usbmuxd                    USB 通讯                             │  │
│  │   ├─ ios tunnel --userspace     iOS 17+ 开发者服务隧道(不建网卡)    │  │
│  │   ├─ pymobiledevice3 usbmux forward  WDA 端口 → 127.0.0.1:8100        │  │
│  │   ├─ pymobiledevice3 usbmux forward  MJPEG stream → 127.0.0.1:9100    │  │
│  │   ├─ pymobiledevice3 webinspector cdp  WebViews → :9222(默认关闭)     │  │
│  │   ├─ ios runwda                 启动手机上的 WebDriverAgent          │  │
│  │   └─ resign-wda.sh(定期)       免费 Apple ID 重签                   │  │
│  │ iphone-mcp(Python,MCP 服务)                                         │  │
│  │   ├─ WDA HTTP(主路线)                                              │  │
│  │   └─ pymobiledevice3 CoreDevice HID(后备路线)                       │  │
│  │ /data ← 宿主机 DATA_DIR                                              │  │
│  └──────────────────────────────┬────────────────────────────────────────┘  │
└─────────────────────────────────┼──────────────────────────────────────────┘
                                  │ USB
                       iPhone(开发者模式,WDA 已签名安装)
```

## 两条控制路线

| | WebDriverAgent | CoreDevice HID |
|---|---|---|
| 能力 | 元素树、按控件点击、输入(含中文)、启动 App、截图 | 截图、按坐标点击/拖动、英文输入、硬件键 |
| 前提 | 用免费 Apple ID 签名(7 天有效),手机上信任开发者 | iOS 27+,开发者镜像已挂载,手机未锁屏 |
| 速度 | 常驻 HTTP,约 1 秒 | 每条命令重建隧道,2~5 秒 |

MCP 工具优先走 WDA;WDA 连不上时,截图、点击、滑动、按键、英文输入自动改走 HID。
坐标统一用「点」(pt):截图已缩放到点尺寸,图上的像素坐标可以直接拿去点。

## 守护(supervisor.sh)

| 检测到 | 处理 |
|---|---|
| USB 上有 Apple 设备,但 usbmuxd 看不到 | 30 秒后重启 usbmuxd(容器里没有 udev,收不到热插拔) |
| 手机离线超过 `OFFLINE_ALERT_MIN` 分钟 | 推送提醒;重新连上再推一条 |
| 隧道 90 秒没建立 | 重启隧道(go-ios 失败后有时不再重试) |
| 端口转发不在,或换了手机 | 重新拉起 |
| WDA 连续 30 秒不响应 | 先补挂开发者镜像,再重启 WDA;失败后间隔 1→2→4→5 分钟 |
| WDA 卡在「Enable UI Automation」密码框 | 推送「请输锁屏密码」,保持每分钟重试;恢复后推送「已恢复」 |
| 本机 runwda 进程不在 | 即使手机上残留的 WDA 还在响应,也视为不可用(它几十秒后会自己退出) |
| 每 `RESIGN_CHECK_HOURS` 小时 | 运行 resign-wda.sh,描述文件剩余不足 `RESIGN_MIN_DAYS` 天才真正重签 |

## 签名和重签(resign-wda.sh)

```
plumesign sign --apple-id     用 Apple ID 申请新描述文件和证书,Bundle ID 改成带团队 ID 的
        │                     (它漏签 .xctest 插件,签出来的包 WDA 起不来,所以只取材料)
        ▼
build-p12.py                  从包里取出描述文件和证书,和 plumesign 保存的私钥拼成 P12;
        │                     核对描述文件里有这台手机
        ▼
ios sign app                  go-ios 用 P12 重新签名,包括 .xctest 插件和里面的框架
        ▼
ios install                   安装成功后才替换旧证书,记下团队 ID 和 Bundle ID
```

开发证书有效期一年,描述文件 7 天。失败时写 `data/logs/ALERT-resign` 并推送通知(20 小时内不重复推)。

## 自动解锁(可选)

配置了 `data/secrets/passcode` 才启用。每个操作类 MCP 工具执行前:

1. WDA 报告锁屏 → 按 Home 唤醒,从底部上滑调出密码键盘。
2. 读锁屏密码栏的值(「共 6 位数，已输入 0 位」),核对位数和配置一致、当前没有残留输入。
3. 逐位按键,每按一位都核对「已输入 N 位」正好加 1;对不上立即停止。输入不完整不算输错。
4. 整串输完仍锁着才算输错一次:写 `data/logs/UNLOCK-DISABLED` 停用自动解锁并推送通知。

实现细节都来自实测:键盘不显示时它的按键也常留在元素树里;锁屏界面一直有动画,
WDA 默认每个请求等界面静止最多 10 秒,解锁期间压到 1 秒;`/wda/tap` 在锁屏上要 2.9 秒,
改用单个 W3C 触摸手势约 0.7 秒;几位合成一个手势会漏键。

## 数据目录

容器内 `/data`,对应宿主机 `DATA_DIR`(默认 `./data`):

| 目录 | 内容 | 敏感 |
|---|---|---|
| `lockdown/` | 配对记录(`/var/lib/lockdown` 指向这里) | 是 |
| `plume/` | Apple ID 登录状态、开发私钥 | **是** |
| `cert/` | P12、密码、描述文件 | **是** |
| `secrets/` | 锁屏密码 | **是** |
| `pmd3/` | 开发者镜像缓存 | 否 |
| `wda/` | 签好的 WDA 包 | 否 |
| `state/` | 团队 ID、WDA Bundle ID、屏幕尺寸缓存 | 否 |
| `logs/` | 各组件日志,超过 5MB 轮转 | 含 UDID |
