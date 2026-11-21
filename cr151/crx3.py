#!/usr/bin/env python3
"""Pack a directory into a CRX3 file signed with an RSA key, and print the extension id.

usage: crx3.py <extension dir> <key.pem> <out.crx>
A missing key.pem is created (2048-bit RSA). The key only fixes the extension id: Chrome derives the id from it, so the
same key keeps the same id, and the profile keeps the extension's settings across versions.

Why a CRX at all: Chrome indexes every declarativeNetRequest ruleset of an unpacked (--load-extension) extension on
the UI thread at every start. A packed extension installed from an external_crx is indexed once, at install.
Format: https://chromium.googlesource.com/chromium/src/+/main/components/crx_file/crx3.proto (CrxFileHeader).
"""
import hashlib
import io
import os
import struct
import subprocess
import sys
import zipfile


def varint(n):
    out = b""
    while True:
        b, n = n & 0x7F, n >> 7
        out += bytes([b | (0x80 if n else 0)])
        if not n:
            return out


def field(num, data):   # protobuf length-delimited field
    return varint(num << 3 | 2) + varint(len(data)) + data


def zip_dir(src):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(src):
            dirs.sort()
            for name in sorted(files):
                path = os.path.join(root, name)
                rel = os.path.relpath(path, src)
                if rel.split(os.sep)[0] == "_metadata":
                    continue   # Chrome's own output in an unpacked folder
                info = zipfile.ZipInfo(rel, date_time=(2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                with open(path, "rb") as f:
                    z.writestr(info, f.read())
    return buf.getvalue()


def main():
    src, key, out = sys.argv[1:4]
    if not os.path.exists(key):
        subprocess.run(["openssl", "genrsa", "-out", key, "2048"], check=True, capture_output=True)
    pub = subprocess.run(["openssl", "rsa", "-in", key, "-pubout", "-outform", "DER"],
                         check=True, capture_output=True).stdout
    crx_id = hashlib.sha256(pub).digest()[:16]
    signed_data = field(1, crx_id)   # SignedData.crx_id
    archive = zip_dir(src)
    msg = b"CRX3 SignedData\x00" + struct.pack("<I", len(signed_data)) + signed_data + archive
    sig = subprocess.run(["openssl", "dgst", "-sha256", "-sign", key], input=msg,
                         check=True, capture_output=True).stdout
    header = field(2, field(1, pub) + field(2, sig)) + field(10000, signed_data)   # sha256_with_rsa, signed_header_data
    with open(out, "wb") as f:
        f.write(b"Cr24" + struct.pack("<II", 3, len(header)) + header + archive)
    print("".join(chr(ord("a") + int(c, 16)) for c in crx_id.hex()))


if __name__ == "__main__":
    main()
