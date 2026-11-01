# 第三方组件

本项目自己的代码(`src/`、`container/`、`bin/`、`tests/`)使用 MIT 许可证。
镜像里还包含下列上游项目,全部**原样**构建、未做修改,通过命令行调用,没有链接进本项目的代码。
版本锁定在 `docker/Dockerfile` 的 `ARG` 和 `docker/constraints-*.txt` 里,升级时同步更新本表。

| 组件 | 版本 | 许可证 | 来源 | 镜像里的位置 | 用途 |
|---|---|---|---|---|---|
| go-ios | 提交 `51887da850dd19f4242c58a00262d06e006839cf` | MIT | https://github.com/danielpaulus/go-ios | `/usr/local/bin/ios` | 用户态隧道、启动 WDA、签名、安装、列 App |
| plumesign(Impactor) | `v2.7.2`(提交 `b13d99559febd63e3710dfdd0ef8cdd78d10ae13`) | MIT | https://github.com/claration/impactor | `/usr/local/bin/plumesign` | Apple ID 登录、注册设备、申请描述文件 |
| pymobiledevice3 | `v11.49.0` | **GPL-3.0** | https://github.com/doronz88/pymobiledevice3 | `/opt/pmd3` | HID 触摸/截图、开发者镜像挂载、端口转发、开发者模式 |
| WebDriverAgent | `v16.15.3`,Appium 官方构建,sha256 `2176793538d902f6b1e61291e9997f68d306541f222ea715d256a7c6ce9d4fc5` | BSD-3-Clause | https://github.com/appium/WebDriverAgent | `/opt/ictl/wda/WDA-unsigned.ipa` | 手机端代理:元素树、点击、输入 |
| usbmuxd | Debian trixie 软件包 | **GPL-3.0** | https://github.com/libimobiledevice/usbmuxd ,源码包见 Debian | `/usr/sbin/usbmuxd` | USB 通讯守护进程 |
| libimobiledevice-utils | Debian trixie 软件包 | LGPL-2.1 / GPL-2.0 | https://github.com/libimobiledevice/libimobiledevice | `/usr/bin/idevice*` | 配对、设备信息 |
| MCP Python SDK | `2.3.0` | MIT | https://github.com/modelcontextprotocol/python-sdk | `/opt/mcp` | MCP 服务框架 |
| Pillow | `13.0.0` | MIT-CMU | https://github.com/python-pillow/Pillow | `/opt/mcp`、`/opt/pmd3` | 截图缩放 |

pymobiledevice3 和 Python 间接依赖的完整版本清单见 `docker/constraints-pmd3.txt`、`docker/constraints-mcp.txt`。
上游许可证原文在镜像的 `/usr/share/licenses/` 和各 Python 包的 `dist-info` 目录里。

## GPL 组件和对应源码

pymobiledevice3、usbmuxd 等是 GPL/LGPL 组件,作为独立程序随镜像分发、通过命令行调用。

发布的镜像 `ghcr.io/derrors/iphone-control-toolkit` 由 GitHub Actions 从本仓库构建
(`.github/workflows/release.yml`)。**每个 Release 都附上镜像里所有第三方组件的完整对应源码**,
由 `scripts/collect-sources.sh` 生成:

| 附件 | 内容 |
|---|---|
| `sources-debian.tar` | 镜像里每个 Debian 软件包的源码包 |
| `sources-python.tar` | 镜像里每个 Python 包的源码发行版 |
| `sources-upstream.tar` | go-ios、Impactor、pymobiledevice3 按锁定版本打包的源码 |
| `SOURCES.md` | 上述全部组件和版本的清单 |

自己分发构建好的镜像时,同样需要提供这些源码,可以用 `scripts/collect-sources.sh <镜像> <目录>` 生成。

## 不包含、也不能包含的东西

- 苹果的开发者磁盘镜像(DDI)和 XCTest 框架:运行时由 pymobiledevice3 从苹果下载,缓存在用户自己的数据目录。
- 任何证书、描述文件、配对记录、Apple ID 登录状态:都在运行时生成,只存在用户的 `data/` 目录。

## 运行时访问的外部服务

- 苹果的开发者服务和 TSS 签发服务(登录、申请描述文件、个性化开发者镜像)。
- plumesign 登录时会请求第三方 anisette 服务(默认 `mac-ani.jkcoxson.com`),用来生成模拟 Mac 的设备标识。
  它拿不到你的 Apple ID 密码,但你应当知道这个依赖。
