#!/bin/sh
# 逐层诊断:USB → usbmuxd → 配对 → 开发者模式 → 开发者镜像 → 隧道 → Apple ID / 签名 → WDA → 附加功能。
# 设备链路上某一层不通,后面依赖它的检查就跳过。退出码 = 失败项数。
# shellcheck source=container/lib.sh
. /opt/ictl/lib.sh

fails=0; blocked=""
ok()   { echo "✅ $1${2:+  $2}"; }
warn() { echo "⚠️  $1${2:+  $2}"; }
bad()  { echo "❌ $1${2:+  $2}"; [ -n "${3:-}" ] && echo "     → $3"; fails=$((fails + 1)); }
skip() { echo "⏭  $1  (跳过:$blocked)"; }
check() { [ -z "$blocked" ]; }

echo "== 设备连接"
if pgrep -x usbmuxd >/dev/null; then ok "usbmuxd 在运行"; else
  bad "usbmuxd 没在运行" "" "iphonectl restart"; blocked="usbmuxd 未运行"; fi

if grep -qs '^05ac$' /sys/bus/usb/devices/*/idVendor; then ok "USB 上有 Apple 设备"; else
  check && { bad "USB 上没有 Apple 设备" "" "插好数据线;用 USB-C 转接头的话换一根试试"; blocked="手机未连接"; }; fi

UDID=$(udid)
if check; then
  if [ -n "$UDID" ]; then ok "usbmuxd 看到手机" "$UDID"; else
    bad "usbmuxd 看不到手机" "" "等 30 秒,supervisor 会自动重启 usbmuxd;仍不行就 iphonectl restart"
    blocked="usbmuxd 看不到手机"; fi
fi

if check; then
  if [ -f "/var/lib/lockdown/$UDID.plist" ]; then
    ver=$(ideviceinfo -u "$UDID" -k ProductVersion 2>/dev/null)
    model=$(ideviceinfo -u "$UDID" -k ProductType 2>/dev/null)
    ok "已配对" "$model iOS $ver"
    major=${ver%%.*}
    if [ -n "$major" ] && [ "$major" -lt 17 ] 2>/dev/null; then
      warn "iOS 低于 17" "未在此版本测试过"
    elif [ -n "$major" ] && [ "$major" -lt 27 ] 2>/dev/null; then
      warn "iOS 低于 27" "HID 后备路线(免签名截图/点击)不可用,只能走 WDA"
    fi
  else
    bad "还没配对" "" "iphonectl setup(手机上要点「信任」并输入锁屏密码)"; blocked="未配对"
  fi
else skip "配对"; fi

echo "== 开发者服务"
if check; then
  dm=$(timeout 60 pymobiledevice3 amfi developer-mode-status --udid "$UDID" 2>/dev/null | tail -n 1)
  case $dm in
    true) ok "开发者模式已打开" ;;
    false) bad "开发者模式没打开" "" "iphonectl setup 会引导打开(手机会重启一次)"; blocked="开发者模式未打开" ;;
    *) bad "读不到开发者模式状态" "" "解锁手机后重试"; blocked="读不到开发者模式" ;;
  esac
else skip "开发者模式"; fi

if check; then
  if ios tunnel ls 2>/dev/null | grep -q "$UDID"; then ok "go-ios 隧道已建立"; else
    bad "go-ios 隧道没建立" "" "解锁手机;锁屏时建不起来(PasswordProtected)"; fi
  mounted=$(timeout 90 pymobiledevice3 mounter list --udid "$UDID" 2>/dev/null | grep -c '"IsMounted": true')
  if [ "${mounted:-0}" -gt 0 ]; then ok "开发者镜像已挂载"; else
    warn "开发者镜像未挂载或读不到" "supervisor 启动 WDA 前会自动挂载;手机要处于解锁状态"; fi
else skip "隧道和开发者镜像"; fi

echo "== Apple ID 与签名"
if plumesign account list 2>&1 | grep -q '(selected)'; then ok "已登录 Apple ID"; else
  bad "没有登录 Apple ID" "" "iphonectl login"; fi

bundle=$(wda_bundle)
if [ -n "$bundle" ]; then ok "WDA 已签名" "$bundle"; else bad "WDA 还没签名安装" "" "iphonectl setup"; fi
left=$(profile_hours_left)
if [ "$left" -lt 0 ]; then
  [ -n "$bundle" ] && bad "描述文件已过期或缺失" "" "iphonectl resign --force"
elif [ "$left" -lt 48 ]; then warn "描述文件只剩 ${left} 小时" "supervisor 会自动重签"
else ok "描述文件有效" "还剩 $((left / 24)) 天"; fi
if [ -f "$LOG_DIR/ALERT-resign" ]; then bad "上次重签失败" "$(cat "$LOG_DIR/ALERT-resign")" "看 data/logs/resign.log"; fi

echo "== WDA"
if check && [ -n "$bundle" ]; then
  if curl -s -m 5 "http://127.0.0.1:$WDA_PORT/status" | grep -Eq '"ready" ?: ?true'; then
    ok "WDA 就绪" "http://127.0.0.1:$WDA_PORT"
  elif grep -qs 'enabling automation mode' "$LOG_DIR/wda.log"; then
    bad "WDA 卡在手机上的密码框" "" "手机重启后首次要在「为 XCTest 输入 iPhone 密码」弹窗里输锁屏密码"
  else
    bad "WDA 不可用" "" "首次安装要在 设置 → 通用 → VPN 与设备管理 里信任开发者;看 data/logs/wda.log"
  fi
else skip "WDA"; fi

echo "== 附加功能"
if [ -n "${TG_BOT_TOKEN:-}${BARK_KEY:-}" ]; then ok "通知已配置" "测试:iphonectl notify-test"; else
  warn "没有配置通知" "重签失败、手机离线、需要输密码时不会提醒你"; fi
if [ -f "$SECRETS_DIR/passcode" ]; then
  if [ -f "$LOG_DIR/UNLOCK-DISABLED" ]; then bad "自动解锁已停用(之前输错过)" "$(cat "$LOG_DIR/UNLOCK-DISABLED")" "核对密码后 iphonectl unlock-reset"
  else ok "自动解锁已启用"; fi
else warn "自动解锁未启用" "手机锁屏时需要人工解锁(可选:iphonectl passcode set)"; fi

echo
if [ "$fails" -eq 0 ]; then echo "全部正常"; else echo "$fails 项需要处理"; fi
exit "$fails"
