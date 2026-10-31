# 故障排查

先跑 `bin/iphonectl doctor`,它会逐层检查并给出修复办法。下面是实际遇到过的问题。

## 连接

| 现象 | 原因 | 处理 |
|---|---|---|
| 手机重插或重启后,usbmuxd 看不到手机 | 容器里没有 udev,usbmuxd 收不到热插拔通知 | supervisor 30 秒内自动重启 usbmuxd;不行就 `iphonectl restart` |
| 隧道报 `PasswordProtected` | 手机锁屏时不给建隧道 | 解锁手机;隧道 90 秒没建起来会自动重启 |
| `ios tunnel` 失败一次后不再重试 | go-ios 的行为 | supervisor 会重启它 |
| 宿主机重启后容器没起来 | 偶发,原因未确认 | `iphonectl up`;建议用 `iphonectl status` 确认 |
| `lsusb` 里没有 iPhone,内核日志也没有任何 USB 事件 | 线或接口没接通,或者是只能充电的线 | 换口、换一根能传数据的线;手机屏幕应显示正在充电 |

## WebDriverAgent

| 现象 | 原因 | 处理 |
|---|---|---|
| `Failed to load the test bundle (Error 103)` | `.xctest` 插件没签名。plumesign 签名会漏掉它 | 本项目用 go-ios 签名,不会出现;自己签时注意 |
| `Timed out while enabling automation mode` | 手机重启后首次启用 UI 自动化,要在「为 XCTest 输入 iPhone 密码」弹窗里输锁屏密码 | 在手机上输;弹窗关掉的话 1 分钟内会重新弹出;配了通知会推送提醒 |
| 输完 XCTest 密码后,下一次启动报 `cannot initiate a IDE session`(超时) | go-ios 的行为,手机刚完成授权时偶发 | 不用处理,supervisor 约 1 分钟后重试即恢复 |
| WDA 装好了但起不来 | 没在手机上信任开发者 | 设置 → 通用 → VPN 与设备管理 → 信任 |
| 容器刚重启时 WDA 显示就绪,几十秒后又挂了 | 手机上残留的旧 WDA 还在响应,随后自己退出 | supervisor 只在本机 runwda 进程存在时才认就绪,会立即重启 WDA |
| 读元素树很慢(7~8 秒) | WDA 计算每个元素的可见性 | MCP 已经排除这些属性(约 0.3 秒),按坐标判断可见性 |

## MCP 工具

| 现象 | 原因 | 处理 |
|---|---|---|
| 按名字启动「设置」打开了黑屏 | 系统里有 5 个后台服务也叫「设置」 | 已跳过带 `hidden` 标记的 App |
| 刚启动的 App 点了没反应 | 冷启动时界面还没准备好,点击被吞掉 | `iphone_launch_app` 会等 App 到前台再停 1 秒 |
| 游戏里 `iphone_list_elements` 返回空 | 游戏引擎把画面画在一块画布上,没有控件 | 用截图加坐标;小图标用区域放大 |
| 被弹窗挡住的元素也列出来了 | 可见性按坐标判断 | 截图核对 |

## 自动解锁

| 现象 | 原因 | 处理 |
|---|---|---|
| 「调不出锁屏密码键盘」 | 唤醒或上滑没生效 | 一位都没输,可以直接重试;反复出现就截图看看锁屏界面 |
| 「第 N 位没按上,已停止」 | 按键没被键盘接住 | 不算输错,稍后重试 |
| 「自动解锁已停用」 | 之前整串输完仍锁着,可能密码配置错了 | 人工解锁,`iphonectl passcode set` 重设密码,再 `iphonectl unlock-reset` |
| 手机重启后自动解锁不工作 | 重启后首次解锁前开发者服务都不可用 | 人工解锁一次 |

## 签名

| 现象 | 处理 |
|---|---|
| plumesign 申请描述文件失败 | 多半是 Apple ID 登录过期:`iphonectl login`,再 `iphonectl resign --force` |
| 「描述文件里没有这台手机」 | 换了手机或没注册:`iphonectl setup` 会注册 |
| 每 7 天要重签 | 免费账号的限制,自动处理;付费开发者账号可以签一年 |
