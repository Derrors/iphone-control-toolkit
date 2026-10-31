#!/bin/sh
# 用免费 Apple ID 给 WDA 签名并装到手机。
# 描述文件剩余超过 RESIGN_MIN_DAYS 天就跳过;--force 强制重签(首次安装也用它)。
# 失败时写 data/logs/ALERT-resign 并推送通知(20 小时内同一告警只推一次)。
set -u
# shellcheck source=container/lib.sh
. /opt/ictl/lib.sh
MIN_DAYS=${RESIGN_MIN_DAYS:-2}
ALERT=$LOG_DIR/ALERT-resign
mkdir -p "$LOG_DIR"

say() { echo "$(date '+%F %T') $*" | tee -a "$LOG_DIR/resign.log"; }
alert() {
  say "失败: $*"
  if [ ! -f "$ALERT" ] || [ -n "$(find "$ALERT" -mmin +1200)" ]; then
    /opt/ictl/notify.sh "iPhone WDA 重签失败" "$*
描述文件过期后 WDA 将无法启动(截图/点击的 HID 路线不受影响)。
排查: iphonectl doctor;日志: data/logs/resign.log" >> "$LOG_DIR/notify.log" 2>&1
  fi
  echo "$(date '+%F %T') $*" > "$ALERT"
  exit 1
}

if [ "${1:-}" != "--force" ]; then
  left=$(profile_hours_left)
  if [ "$left" -gt $((MIN_DAYS * 24)) ]; then
    say "描述文件还剩 ${left} 小时,无需重签"; exit 0
  fi
fi

UDID=$(udid)
[ -n "$UDID" ] || alert "手机未连接"
plumesign account list 2>/dev/null | grep -q '(selected)' \
  || alert "还没有登录 Apple ID,或登录已失效:运行 iphonectl login"

WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
say "开始重签"

# 1. plumesign 用 Apple ID 申请新的描述文件和证书(它会把 Bundle ID 改成带团队 ID 的)
RUST_LOG=warn timeout 300 plumesign sign -p "$WDA_UNSIGNED" --apple-id -o "$WORK/plume.ipa" \
  > "$WORK/plume.log" 2>&1 \
  || { tail -5 "$WORK/plume.log" >> "$LOG_DIR/resign.log"; alert "plumesign 申请描述文件失败,可能需要重新登录 Apple ID(iphonectl login)"; }

# 2. plumesign 漏签 .xctest 插件,只取它的描述文件和证书,组装成 P12
mkdir -p "$WORK/cert"
/opt/pmd3/bin/python -I /opt/ictl/build-p12.py "$WORK/plume.ipa" "$PLUME_DIR/keys" "$WORK/cert" "$UDID" \
  > "$WORK/p12.out" 2>> "$LOG_DIR/resign.log"
case $? in
  0) ;;
  3) alert "描述文件里没有这台手机,手机还没注册到 Apple ID:运行 iphonectl setup" ;;
  *) alert "组装 P12 失败" ;;
esac
TEAM=$(sed -n 's/^team=//p' "$WORK/p12.out")
BUNDLE=$(sed -n 's/^bundle=//p' "$WORK/p12.out")
EXPIRES=$(sed -n 's/^expires=//p' "$WORK/p12.out")

# 3. go-ios 签名(会签上 .xctest 插件和里面的框架)并安装
ios sign app --path="$WDA_UNSIGNED" --p12file="$WORK/cert/free-dev.p12" \
  --p12password="$(cat "$WORK/cert/p12password.txt")" --profile="$WORK/cert/free-dev.mobileprovision" \
  --bundleid="$BUNDLE" --output="$WORK/signed.ipa" > "$WORK/sign.log" 2>&1 \
  || { tail -3 "$WORK/sign.log" >> "$LOG_DIR/resign.log"; alert "go-ios 签名失败"; }

ios install --udid="$UDID" --path="$WORK/signed.ipa" > "$WORK/install.log" 2>&1
grep -q "installation successful" "$WORK/install.log" \
  || { tail -3 "$WORK/install.log" >> "$LOG_DIR/resign.log"; alert "安装到手机失败(手机锁屏?)"; }

# 安装成功后才替换旧文件
for f in free-dev.p12 p12password.txt free-dev.mobileprovision; do
  mv -f "$WORK/cert/$f" "$CERT_DIR/$f"
done
mv -f "$WORK/signed.ipa" "$WDA_DIR/WDA-signed.ipa"
echo "$TEAM" > "$STATE_DIR/team"
echo "$BUNDLE" > "$STATE_DIR/wda-bundle"
fix_owner

# 新包装上后旧的 WDA 进程会失效,supervisor 检测到后自动拉起
pkill -f '^ios runwda'
rm -f "$ALERT"
say "重签完成,新描述文件到期 $EXPIRES"
