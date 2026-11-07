# 容器内各脚本共用的配置和函数(POSIX sh,用 . 引入)
# shellcheck shell=sh disable=SC2034  # 变量给引入它的脚本用

DATA=${ICTL_DATA:-/data}
LOG_DIR=$DATA/logs
CERT_DIR=$DATA/cert
WDA_DIR=$DATA/wda
STATE_DIR=$DATA/state
SECRETS_DIR=$DATA/secrets
PLUME_DIR=$DATA/plume
WDA_PORT=${WDA_PORT:-8100}
# Live screen (WDA's MJPEG stream) and WebView debugging (Chrome DevTools Protocol) ports, 127.0.0.1 only; 0 = off.
# CDP stays off unless asked for: it gives access to the phone's logged-in Safari tabs
MJPEG_PORT=${MJPEG_PORT:-9100}
CDP_PORT=${CDP_PORT:-0}
WDA_UNSIGNED=/opt/ictl/wda/WDA-unsigned.ipa
PROFILE=$CERT_DIR/free-dev.mobileprovision
PUID=${PUID:-1000}
PGID=${PGID:-1000}

log() { echo "$(date '+%F %T') $*" >> "$LOG_DIR/${LOG_NAME:-supervisor}.log"; }

# 要操作的手机:.env 里指定了 IPHONE_UDID 就用它(要求已连接),否则用 usbmuxd 看到的第一台
udid() {
  if [ -n "${IPHONE_UDID:-}" ]; then
    idevice_id -l 2>/dev/null | grep -x "$IPHONE_UDID"
  else
    idevice_id -l 2>/dev/null | head -n 1
  fi
}

# 签名后才知道:免费账号的团队 ID 和 plumesign 改过的 WDA Bundle ID,由 resign-wda.sh 写入
team()       { cat "$STATE_DIR/team" 2>/dev/null; }
wda_bundle() { cat "$STATE_DIR/wda-bundle" 2>/dev/null; }

# 描述文件还剩几小时;没有描述文件输出 -1
profile_hours_left() {
  [ -f "$PROFILE" ] || { echo -1; return; }
  python3 -I -c '
import datetime, plistlib, sys
r = open(sys.argv[1], "rb").read()
d = plistlib.loads(r[r.index(b"<?xml"):r.index(b"</plist>") + 8])
now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
print(int((d["ExpirationDate"] - now).total_seconds() // 3600))' "$PROFILE"
}

# 容器里以 root 运行,数据目录要还给宿主机用户,才能直接看日志、备份
fix_owner() { chown -R "$PUID:$PGID" "$DATA" 2>/dev/null || true; }

# 后台发通知,不阻塞调用方;没配置通知渠道时 notify.sh 静默跳过
notify() { /opt/ictl/notify.sh "$1" "$2" >> "$LOG_DIR/notify.log" 2>&1 & }
