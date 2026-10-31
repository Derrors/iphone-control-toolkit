#!/bin/sh
# 容器入口:准备数据目录,然后交给 supervisor
set -e
# shellcheck source=container/lib.sh
. /opt/ictl/lib.sh

# /var/lib/lockdown、plumesign 和 pymobiledevice3 的状态目录在镜像里已是指向这些目录的符号链接
mkdir -p "$DATA/lockdown" "$PLUME_DIR" "$DATA/pmd3" "$LOG_DIR" "$CERT_DIR" "$WDA_DIR" "$STATE_DIR" "$SECRETS_DIR"
# 配对记录里有私钥,usbmuxd 会把 lockdown 改成 2775,所以把整个数据目录收紧到 700
chmod 700 "$DATA" "$PLUME_DIR" "$CERT_DIR" "$SECRETS_DIR"
fix_owner

exec /opt/ictl/supervisor.sh
