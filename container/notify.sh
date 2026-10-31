#!/bin/sh
# 发通知到 Telegram / Bark。配置来自环境变量(.env),配了哪个渠道就发哪个。
# 用法: notify.sh <标题> <正文>     notify.sh --test 发一条测试消息
# 代理沿用 HTTPS_PROXY;自建在局域网的 Bark 记得加进 NO_PROXY。

if [ "${1:-}" = "--test" ]; then
  test=1; title="iPhone 控制:测试通知"; body="通知通道正常 $(date '+%F %T')"
else
  test=0; title=$1; body=${2:-}
fi

sent=0; failed=""
if [ -n "${TG_BOT_TOKEN:-}" ] && [ -n "${TG_CHAT_ID:-}" ]; then
  if curl -fsS -m 20 -o /dev/null "https://api.telegram.org/bot$TG_BOT_TOKEN/sendMessage" \
      --data-urlencode "chat_id=$TG_CHAT_ID" --data-urlencode "text=$title
$body"; then
    sent=$((sent + 1))
  else
    failed="$failed Telegram"
  fi
fi
if [ -n "${BARK_KEY:-}" ]; then
  if curl -fsS -m 20 -o /dev/null "${BARK_SERVER:-https://api.day.app}/$BARK_KEY" \
      --data-urlencode "title=$title" --data-urlencode "body=$body" --data-urlencode "group=iPhone"; then
    sent=$((sent + 1))
  else
    failed="$failed Bark"
  fi
fi

if [ "$sent" -eq 0 ] && [ -z "$failed" ]; then
  [ "$test" -eq 1 ] && { echo "没有配置任何通知渠道(.env 里的 TG_* 或 BARK_*)" >&2; exit 2; }
  exit 0
fi
[ -n "$failed" ] && echo "$(date '+%F %T') 发送失败:$failed | $title" >&2
[ "$sent" -gt 0 ] && echo "$(date '+%F %T') 已发送 $sent 个渠道 | $title"
[ "$sent" -gt 0 ]
