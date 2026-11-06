#!/bin/sh
# 守护进程:usbmuxd / go-ios 用户态隧道 / 端口转发 / WDA,掉线自动恢复;
# 另外定期检查是否需要重签,手机离线太久时推送提醒
# shellcheck source=container/lib.sh
. /opt/ictl/lib.sh

RESIGN_CHECK_HOURS=${RESIGN_CHECK_HOURS:-6}
OFFLINE_ALERT_MIN=${OFFLINE_ALERT_MIN:-10}

rotate() {
  for f in "$LOG_DIR"/*.log; do
    [ -f "$f" ] && [ "$(stat -c %s "$f")" -gt 5242880 ] && mv -f "$f" "$f.1"
  done
}

phys_present() { grep -qs '^05ac$' /sys/bus/usb/devices/*/idVendor; }
running()      { pgrep -f "$1" >/dev/null; }
tunnel_ok()    { ios tunnel ls 2>/dev/null | grep -q "$UDID"; }
# 本机 runwda 退出后,手机上残留的 WDA 还会响应几十秒然后自己退出,不能算就绪
wda_ready()    { running '^ios runwda' && curl -s -m 5 "http://127.0.0.1:$WDA_PORT/status" | grep -Eq '"ready" ?: ?true'; }

# 容器里没有 udev,usbmuxd 收不到热插拔,只能靠重启它重新扫描
start_usbmuxd() {
  pkill -x usbmuxd; sleep 1
  usbmuxd -U root -f >> "$LOG_DIR/usbmuxd.log" 2>&1 &
  log "usbmuxd 已(重新)启动"
}
start_tunnel() {
  pkill -f '^ios tunnel start'; sleep 1
  ios tunnel start --userspace --udid="$UDID" >> "$LOG_DIR/tunnel.log" 2>&1 &
  log "隧道已(重新)启动"
}
# 不用 ios forward:它监听所有网卡,而 WDA 没有认证;pymobiledevice3 的转发默认只绑 127.0.0.1
# One forward process per port, identified by UDID and port: restarted when the phone changes, independent of each other.
ensure_forward() {
  [ "$1" -gt 0 ] || return 0
  running "usbmux forward --udid $UDID $1 $1\$" && return 0
  pkill -f "usbmux forward --udid .* $1 $1\$"; sleep 1
  pymobiledevice3 usbmux forward --udid "$UDID" "$1" "$1" >> "$LOG_DIR/forward.log" 2>&1 &
  log "Port forward 127.0.0.1:$1 started"
}

# WebView debugging: serves the phone's Safari tabs and inspectable WebViews over the Chrome DevTools Protocol.
# Needs Settings → Apps → Safari → Advanced → Web Inspector on the phone, and isInspectable on an app's WKWebView.
ensure_cdp() {
  [ "$CDP_PORT" -gt 0 ] || return 0
  running "webinspector cdp --udid $UDID " && return 0
  pkill -f 'webinspector cdp'; sleep 1
  pymobiledevice3 webinspector cdp --udid "$UDID" --host 127.0.0.1 --port "$CDP_PORT" >> "$LOG_DIR/cdp.log" 2>&1 &
  log "CDP bridge 127.0.0.1:$CDP_PORT started"
}
# 手机重启后开发者镜像会掉;已挂载时 auto-mount 约 1 秒直接跳过
start_wda() {
  pkill -f '^ios runwda'; sleep 1
  timeout 120 pymobiledevice3 mounter auto-mount --udid "$UDID" >> "$LOG_DIR/mount.log" 2>&1
  ios runwda --udid="$UDID" --bundleid="$1" --testrunnerbundleid="$1" \
    --xctestconfig=WebDriverAgentRunner.xctest > "$LOG_DIR/wda.log" 2>&1 &
  log "WDA 已(重新)启动"
}

trap 'log "收到停止信号,退出"; pkill -P $$; exit 0' TERM INT

log "supervisor 启动"
start_usbmuxd
state=""; miss=0; tun_bad=0; wda_fail=0; wda_next=0; wda_backoff=60
wda_up=0; pin_notified=0; no_bundle_logged=0
offline_since=$(date +%s); offline_notified=0; next_resign=0; tick=0

while :; do
  tick=$((tick + 1))
  [ $((tick % 30)) -eq 1 ] && { rotate; fix_owner; }
  now=$(date +%s)

  UDID=$(udid)
  if [ -z "$UDID" ]; then
    if phys_present; then
      miss=$((miss + 1))
      if [ "$miss" -ge 3 ]; then
        log "USB 上有 Apple 设备但 usbmuxd 看不到,重启 usbmuxd"
        start_usbmuxd; miss=0
      fi
    fi
    if [ "$state" != offline ]; then
      log "手机离线"; state=offline; offline_since=$now
    fi
    if [ "$OFFLINE_ALERT_MIN" -gt 0 ] && [ "$offline_notified" -eq 0 ] \
        && [ $((now - offline_since)) -ge $((OFFLINE_ALERT_MIN * 60)) ]; then
      notify "iPhone 已离线 ${OFFLINE_ALERT_MIN} 分钟" "NAS 连不上手机:检查 USB 线、手机是否没电关机。重新连上后会自动恢复。"
      offline_notified=1
    fi
    sleep 10; continue
  fi
  miss=0
  if [ "$state" != online ]; then
    log "手机在线 $UDID"; state=online; wda_next=0; wda_backoff=60
    if [ "$offline_notified" -eq 1 ]; then
      notify "iPhone 已重新连上" "离线约 $(((now - offline_since) / 60)) 分钟,正在自动恢复。"
      offline_notified=0
    fi
  fi

  # 定期检查描述文件,剩余不足 RESIGN_MIN_DAYS 天才真正重签;失败由 resign-wda.sh 自己推送
  if [ "$now" -ge "$next_resign" ] && [ -n "$(wda_bundle)" ] && ! running resign-wda.sh; then
    /opt/ictl/resign-wda.sh >/dev/null 2>&1 &
    next_resign=$((now + RESIGN_CHECK_HOURS * 3600))
  fi

  running '^ios tunnel start' || start_tunnel
  if tunnel_ok; then
    tun_bad=0
  else
    tun_bad=$((tun_bad + 1))
    # go-ios 隧道失败后有时不再重试,90 秒没建起来就重启
    if [ "$tun_bad" -ge 9 ]; then
      log "隧道 90 秒未建立(手机锁屏?),重启隧道"
      start_tunnel; tun_bad=0
    fi
  fi

  ensure_forward "$WDA_PORT"
  ensure_forward "$MJPEG_PORT"
  ensure_cdp

  bundle=$(wda_bundle)
  if [ -z "$bundle" ]; then
    [ "$no_bundle_logged" -eq 0 ] && log "还没有签名安装 WDA,先运行 iphonectl setup"
    no_bundle_logged=1
    sleep 10; continue
  fi

  if wda_ready; then
    [ "$wda_up" -eq 0 ] && log "WDA 就绪"
    if [ "$pin_notified" -eq 1 ]; then
      notify "iPhone WDA 已恢复" "已输入密码,WDA 重新就绪,可以正常操作了。"
      pin_notified=0
    fi
    wda_up=1; wda_fail=0; wda_backoff=60
  else
    wda_fail=$((wda_fail + 1))
    # 连续 3 次(约 30 秒)不通才算挂,避免长请求时误杀
    if [ "$wda_fail" -ge 3 ] && [ "$now" -ge "$wda_next" ] && tunnel_ok; then
      [ "$wda_up" -eq 1 ] && log "WDA 不可用"
      wda_up=0
      # 手机重启后首次启用 UI 自动化,要在手机上输锁屏密码,没人输就超时
      need_pin=0
      if grep -qs 'enabling automation mode' "$LOG_DIR/wda.log"; then
        need_pin=1
        log "WDA 卡在手机上的「Enable UI Automation」密码框:请在手机上输入锁屏密码"
        if [ "$pin_notified" -eq 0 ]; then
          notify "iPhone 需要输入锁屏密码" "手机重启后要启用 UI 自动化:请解锁手机,在「为 XCTest 输入 iPhone 密码」弹窗里输入锁屏密码。弹窗没出现或已关闭的话,1 分钟内会重新弹出。"
          pin_notified=1
        fi
      fi
      start_wda "$bundle"
      wda_next=$((now + wda_backoff))
      wda_backoff=$((wda_backoff * 2)); [ "$wda_backoff" -gt 300 ] && wda_backoff=300
      # 等人输密码时保持 1 分钟重试,输完很快就能起来
      [ "$need_pin" -eq 1 ] && { wda_next=$((now + 60)); wda_backoff=60; }
    fi
  fi
  sleep 10
done
