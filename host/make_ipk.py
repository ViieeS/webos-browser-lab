"""Pack browser/build/app (from bundle.sh) as a native webOS app with the host binary as "main"."""
import json
import os
import sys

# ar/tar_gz and the icon come from github.com/ViieeS/mytvlauncher (a checkout at $MYTVLAUNCHER).
MYTV = os.environ.get("MYTVLAUNCHER", os.path.expanduser("~/Projects/mytvlauncher"))
sys.path.insert(0, os.path.join(MYTV, "tools"))
from make_ipk import ar, tar_gz  # noqa: E402

APP = "com.viiees.browser"
VERSION = "0.0.1"
BUILD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build")
SRC = os.path.join(BUILD, "app")
ROOT = f"usr/palm/applications/{APP}"
PKG = f"usr/palm/packages/{APP}"

info = {"id": APP, "version": VERSION, "vendor": "ViieeS", "type": "native", "main": "browser",
        "title": "Browser", "icon": "icon.png", "requiredMemory": 512}
entries = [(d, None, 0o755) for d in ["usr", "usr/palm", "usr/palm/applications", ROOT,
                                      "usr/palm/packages", PKG]]
entries.append((f"{ROOT}/appinfo.json", json.dumps(info).encode(), 0o644))
entries.append((f"{ROOT}/icon.png",
                open(os.path.join(MYTV, "package", "icon.png"), "rb").read(), 0o644))
for base, dirs, files in os.walk(SRC):
    rel = os.path.relpath(base, SRC)
    for d in sorted(dirs):
        entries.append((os.path.normpath(f"{ROOT}/{rel}/{d}"), None, 0o755))
    for f in sorted(files):
        path = os.path.join(base, f)
        mode = 0o755 if os.access(path, os.X_OK) else 0o644
        entries.append((os.path.normpath(f"{ROOT}/{rel}/{f}"), open(path, "rb").read(), mode))
pinfo = {"app": APP, "id": APP, "loc_name": "Browser", "package_format_version": 2,
         "vendor": "ViieeS", "version": VERSION}
entries.append((f"{PKG}/packageinfo.json", json.dumps(pinfo).encode(), 0o644))

size_kb = sum(len(b) for _, b, _ in entries if b) // 1024
control = (f"Package: {APP}\nVersion: {VERSION}\nSection: misc\nPriority: optional\n"
           f"Architecture: arm\nInstalled-Size: {size_kb}\nMaintainer: ViieeS\nDescription: Browser\n"
           f"webOS-Package-Format-Version: 2\nwebOS-Packager-Version: x.y.x\n").encode()
out = os.path.join(BUILD, f"{APP}_{VERSION}_arm.ipk")
with open(out, "wb") as fh:
    fh.write(ar([("debian-binary", b"2.0\n"),
                 ("control.tar.gz", tar_gz([("control", control, 0o644)])),
                 ("data.tar.gz", tar_gz(entries))]))
print(out, os.path.getsize(out) // 1024 // 1024, "MB")
