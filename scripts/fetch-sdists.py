"""按 `名称==版本` 清单从 PyPI 下载每个包的源码发行版(sdist),不构建、不执行任何包代码。

用法: python3 -I fetch-sdists.py <清单文件> <输出目录>
找不到 sdist 的包打印到 stderr(前缀 MISSING),退出码为缺失数量。
"""
import hashlib
import json
import os
import sys
import urllib.request

reqs, out = sys.argv[1], sys.argv[2]
missing = 0
for line in open(reqs):
    line = line.strip()
    if "==" not in line:
        continue
    name, version = line.split("==", 1)
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=60) as r:
            files = json.load(r)["urls"]
        sdist = next(f for f in files if f["packagetype"] == "sdist")
        with urllib.request.urlopen(sdist["url"], timeout=300) as r:
            data = r.read()
        if hashlib.sha256(data).hexdigest() != sdist["digests"]["sha256"]:
            raise ValueError("sha256 mismatch")
        with open(os.path.join(out, sdist["filename"]), "wb") as f:
            f.write(data)
    except Exception as e:  # 汇报每个失败的包,继续处理其余的
        print(f"MISSING {line}: {e!r}", file=sys.stderr)
        missing += 1
sys.exit(min(missing, 125))
