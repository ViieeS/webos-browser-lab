"""Packs a native binary as a minimal webOS developer app (.ipk), so SAM launches it with the app's identity.
The binary itself is "main": NDL's resource manager exit()s a process whose executable is not the app's main
(a shell main that execs it is not enough).

usage: mkprobeipk.py <binary> <app id> <out.ipk> <icon.png>
"""
import io
import json
import sys
import tarfile

binary, app_id, out = sys.argv[1:4]
MTIME = 1700000000


def tar_gz(entries):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz") as tar:
        for path, data, mode in entries:
            info = tarfile.TarInfo(path)
            info.mtime, info.mode = MTIME, mode
            if data is None:
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
            else:
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    return raw.getvalue()


name = binary.rsplit("/", 1)[-1]
appinfo = {"id": app_id, "version": "0.0.1", "vendor": "ViieeS", "type": "native", "main": name,
           "title": app_id, "icon": "icon.png", "requiredMemory": 64}
icon = open(sys.argv[4], "rb").read()
app = f"usr/palm/applications/{app_id}"
dirs = ["usr", "usr/palm", "usr/palm/applications", app]
data = tar_gz([(d + "/", None, 0o755) for d in dirs] + [
    (f"{app}/appinfo.json", json.dumps(appinfo).encode(), 0o644),
    (f"{app}/{name}", open(binary, "rb").read(), 0o755),
    (f"{app}/icon.png", icon, 0o644),
])
control = tar_gz([("control", (f"Package: {app_id}\nVersion: 0.0.1\nSection: misc\nPriority: optional\n"
                               f"Architecture: arm\nInstalled-Size: 1\nMaintainer: ViieeS\n"
                               f"Description: {app_id}\nwebOS-Package-Format-Version: 2\n"
                               f"webOS-Packager-Version: x.y.x\n").encode(), 0o644)])


def ar_member(name, body):
    hdr = f"{name + '/':<16}{MTIME:<12}{0:<6}{0:<6}{0o100644:<8o}{len(body):<10}`\n".encode()
    return hdr + body + (b"\n" if len(body) % 2 else b"")


with open(out, "wb") as f:
    f.write(b"!<arch>\n" + ar_member("debian-binary", b"2.0\n") + ar_member("control.tar.gz", control)
            + ar_member("data.tar.gz", data))
