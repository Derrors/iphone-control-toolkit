"""从 plumesign 签好的 IPA 里取出描述文件和开发证书,与 plumesign 保存的私钥拼成 P12。

plumesign 漏签 .xctest 插件,所以只用它申请描述文件和证书,真正的签名交给 go-ios(要 P12)。

用法: python3 -I build-p12.py <plumesign 签好的 ipa> <plumesign keys 目录> <输出目录> [UDID]
输出目录里写 free-dev.p12、p12password.txt、free-dev.mobileprovision;
标准输出打印 team=、bundle=、expires= 三行。
给了 UDID 但描述文件里没有这台手机时退出码为 3。
"""
import os
import plistlib
import secrets
import struct
import sys
import zipfile

from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    load_pem_private_key,
    pkcs7,
    pkcs12,
)

ipa, keys_dir, out = sys.argv[1:4]
udid = sys.argv[4] if len(sys.argv) > 4 else None

z = zipfile.ZipFile(ipa)
app = next(n.split("/")[1] for n in z.namelist() if n.startswith("Payload/") and n.endswith(".app/Info.plist"))
info = plistlib.loads(z.read(f"Payload/{app}/Info.plist"))
raw = z.read(f"Payload/{app}/embedded.mobileprovision")
binary = z.read(f"Payload/{app}/{info['CFBundleExecutable']}")
profile = plistlib.loads(raw[raw.index(b"<?xml"):raw.index(b"</plist>") + 8])
team = profile["TeamIdentifier"][0]

if udid and udid not in profile.get("ProvisionedDevices", []):
    print(f"描述文件里没有 {udid},这台手机还没注册到 Apple ID", file=sys.stderr)
    sys.exit(3)

# 代码签名超级块里 0xfade0b01 是 CMS 签名,里面带证书链
i = binary.index(b"\xfa\xde\x0b\x01")
n = struct.unpack(">I", binary[i + 4:i + 8])[0]
certs = pkcs7.load_der_pkcs7_certificates(binary[i + 8:i + n])
key = load_pem_private_key(open(os.path.join(keys_dir, team, "key.pem"), "rb").read(), None)
pub = key.public_key().public_numbers()
leaf = next(c for c in certs if c.public_key().public_numbers() == pub)
others = [c for c in certs if c is not leaf]

pw = secrets.token_urlsafe(16)
os.umask(0o077)
with open(os.path.join(out, "free-dev.p12"), "wb") as f:
    f.write(pkcs12.serialize_key_and_certificates(
        b"free-dev", key, leaf, others, BestAvailableEncryption(pw.encode())))
with open(os.path.join(out, "p12password.txt"), "w") as f:
    f.write(pw)
with open(os.path.join(out, "free-dev.mobileprovision"), "wb") as f:
    f.write(raw)

print(f"team={team}")
print(f"bundle={info['CFBundleIdentifier']}")
print(f"expires={profile['ExpirationDate'].strftime('%Y-%m-%d %H:%M UTC')}")
