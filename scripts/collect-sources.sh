#!/bin/sh
# 收集镜像里 GPL / LGPL 组件的对应源码,作为 Release 附件提供(履行 GPL 的源码提供义务)。
#
# 用法: scripts/collect-sources.sh <镜像> <输出目录>
#
# 收集三类源码:
#   1. 镜像里所有 Debian 软件包的源码包(含 usbmuxd、libimobiledevice 等 GPL/LGPL 组件)
#   2. 镜像里所有 Python 包的源码发行版(sdist),pymobiledevice3 及其 GPL 依赖都在其中
#   3. 从源码编译的上游项目(go-ios、Impactor)按锁定提交打包
# 每类打成一个 tar 包,外加 SOURCES.md 清单和 SHA256SUMS。
set -eu
IMAGE=$1
OUT=$(mkdir -p "$2" && cd "$2" && pwd)
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/debian" "$WORK/python" "$WORK/upstream"

# Dockerfile 里的锁定版本(go-ios 提交、Impactor tag/提交、pymobiledevice3 tag)
DF=$(dirname "$0")/../docker/Dockerfile
arg() { sed -n "s/^ARG $1=//p" "$DF" | head -n 1; }

echo "== 读取镜像里的 Debian 源码包和 Python 包清单"
docker run --rm --entrypoint sh "$IMAGE" -c \
  "dpkg-query -W -f='\${source:Package}=\${source:Version}\n' | sort -u" > "$WORK/debian.list"
docker run --rm --entrypoint sh "$IMAGE" -c \
  '/opt/pmd3/bin/pip freeze --all; /opt/mcp/bin/pip freeze --all' \
  | grep '==' | grep -v -E '^(iphone-mcp|pip|setuptools|wheel)==' | sort -u > "$WORK/python.list"
wc -l "$WORK/debian.list" "$WORK/python.list"

echo "== 下载 Debian 源码包"
# 先从镜像站取;镜像站已不提供的旧版本(被安全更新替换掉的)再去 snapshot.debian.org 取
docker run --rm --network host -v "$WORK/debian:/out" -v "$WORK/debian.list:/list:ro" \
  -v "$(cd "$(dirname "$0")" && pwd)/fetch-debsrc-snapshot.py:/snapshot.py:ro" \
  -e HTTP_PROXY="${HTTP_PROXY:-}" -e HTTPS_PROXY="${HTTPS_PROXY:-}" \
  --entrypoint sh "$IMAGE" -c '
    set -e
    sed -i "s/^Types: deb$/Types: deb deb-src/" /etc/apt/sources.list.d/debian.sources
    apt-get update -qq
    cd /out
    while read -r pkg; do
      apt-get source --download-only -qq "$pkg" 2>/dev/null \
        || python3 -I /snapshot.py "${pkg%%=*}" "${pkg#*=}" /out
    done < /list'

echo "== 下载 Python 源码发行版"
docker run --rm --network host -v "$WORK/python:/out" -v "$WORK/python.list:/list:ro" \
  -v "$(cd "$(dirname "$0")" && pwd)/fetch-sdists.py:/fetch-sdists.py:ro" \
  -e HTTP_PROXY="${HTTP_PROXY:-}" -e HTTPS_PROXY="${HTTPS_PROXY:-}" \
  --entrypoint /opt/pmd3/bin/python "$IMAGE" -I /fetch-sdists.py /list /out

echo "== 打包上游源码"
up() { # 名称 仓库 提交或 tag
  git init -q "$WORK/upstream/$1"
  git -C "$WORK/upstream/$1" fetch -q --depth 1 "$2" "$3"
  git -C "$WORK/upstream/$1" archive --prefix="$1/" -o "$WORK/upstream/$1.tar" FETCH_HEAD
  rm -rf "${WORK:?}/upstream/$1"
}
up go-ios https://github.com/danielpaulus/go-ios "$(arg GOIOS_COMMIT)"
up impactor https://github.com/claration/impactor "$(arg IMPACTOR_COMMIT)"
up pymobiledevice3 https://github.com/doronz88/pymobiledevice3 "refs/tags/$(arg PMD3_TAG)"
gzip -9 "$WORK"/upstream/*.tar

echo "== 生成归档和清单"
tar -C "$WORK" -cf "$OUT/sources-debian.tar" debian
tar -C "$WORK" -cf "$OUT/sources-python.tar" python
tar -C "$WORK" -cf "$OUT/sources-upstream.tar" upstream
{
  echo "# Corresponding source / 对应源码"
  echo
  echo "Source code for the third-party components in image \`$IMAGE\`, provided to meet the"
  echo "source-availability terms of the GPL and LGPL. See THIRD_PARTY.md in the repository."
  echo
  echo "| Archive | Contents |"
  echo "|---|---|"
  echo "| \`sources-debian.tar\` | Debian source packages for every package in the image ($(wc -l < "$WORK/debian.list")) |"
  echo "| \`sources-python.tar\` | Python source distributions for every Python package in the image ($(wc -l < "$WORK/python.list")) |"
  echo "| \`sources-upstream.tar\` | go-ios, Impactor (plumesign) and pymobiledevice3 at the exact pinned revisions |"
  echo
  echo "## Debian source packages"; echo; sed 's/^/- /' "$WORK/debian.list"
  echo; echo "## Python packages"; echo; sed 's/^/- /' "$WORK/python.list"
  echo; echo "## Upstream revisions"; echo
  echo "- go-ios: \`$(arg GOIOS_COMMIT)\`"
  echo "- Impactor: \`$(arg IMPACTOR_TAG)\` (\`$(arg IMPACTOR_COMMIT)\`)"
  echo "- pymobiledevice3: \`$(arg PMD3_TAG)\`"
} > "$OUT/SOURCES.md"
(cd "$OUT" && sha256sum sources-*.tar SOURCES.md > SHA256SUMS-sources)
ls -lh "$OUT"
