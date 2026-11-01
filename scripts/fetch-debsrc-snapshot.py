"""从 snapshot.debian.org 下载指定版本的 Debian 源码包(.dsc 及其引用的全部文件)。

用于镜像站已经不再提供的旧版本(比如被安全更新替换掉的版本)。
用法: python3 -I fetch-debsrc-snapshot.py <源码包名> <版本> <输出目录>
"""
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request

name, version, out = sys.argv[1:4]
api = "https://snapshot.debian.org/mr/package/{}/{}/srcfiles?fileinfo=1".format(
    urllib.parse.quote(name), urllib.parse.quote(version))
with urllib.request.urlopen(api, timeout=60) as r:
    info = json.load(r)

files = info["result"]
if not files:
    sys.exit(f"snapshot.debian.org 上没有 {name} {version}")
for f in files:
    sha1 = f["hash"]
    # 同一文件可能出现在多个归档里,文件名都一样,取第一个
    fname = info["fileinfo"][sha1][0]["name"]
    with urllib.request.urlopen(f"https://snapshot.debian.org/file/{sha1}", timeout=600) as r:
        data = r.read()
    if hashlib.sha1(data).hexdigest() != sha1:
        sys.exit(f"{fname}: sha1 不符")
    with open(os.path.join(out, fname), "wb") as fh:
        fh.write(data)
    print(f"snapshot: {fname}")
