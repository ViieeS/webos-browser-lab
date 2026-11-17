#!/usr/bin/env python3
"""Runs pages/harness.html cases in the stock webOS browser and in ours, the same way for both, and
prints one line per run from the beacons in lighttpd's access log on the TV.
usage: harness_run.py [-b stock,ours,cr120,cr151] <rounds> <case> [case...]
       (cases: micro load-wiki raf-wiki speedometer; default browsers: stock,ours)
cr120 is content_shell from browser/cr120, started from telnet by its run_tv.sh (no SAM app).
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bench  # noqa: E402

ACCESS = "/tmp/bench-access.log"
CEILING = {"micro": 60, "load-wiki": 40, "raf-wiki": 50, "raf-wiki-nojs": 50, "settle-wiki": 50, "settle-wiki-nojs": 50, "speedometer": 1200}
# cr151: WebOS-Chromium (github.com/sarahahzub/WebOS-Chromium) release IPK; its run.sh opens params.target (http/https only)
CR151 = "org.nativechromium.browser"
BROWSERS = {"stock": ("com.webos.app.browser", "target"), "ours": (bench.APP, "url"), "cr120": None,
            "cr151": (CR151, "target")}
CR120 = "sh /media/developer/temp/cr120/run_tv.sh"
CLOSE = "".join(f"luna-send -n 1 luna://com.webos.applicationManager/closeByAppId '{{\"id\":\"{a}\"}}' >/dev/null; "
                for a in ("com.webos.app.browser", bench.APP, CR151, "youtube.leanback.v4")) + f"{CR120} stop; "


def fire(cmd):
    """Launch/close: no reply needed. A telnet session that launches an app often never sends its end
    marker, and tvtelnet then waits its full 180 s, so the session is cut after 30 s."""
    try:
        bench.tv(cmd, timeout=30)
    except subprocess.TimeoutExpired:
        pass


def beacon(tag, case, run):
    out = bench.tv(f"grep 'beacon?tag={tag}&case={case}&run={run}&' {ACCESS} | tail -n 1")
    m = re.search(r"GET /beacon\?(\S+) HTTP", out)
    return dict(urllib.parse.parse_qsl(m.group(1))) if m else None


def run_one(tag, case, run):
    url = f"{bench.HTTP}/pages/harness.html?case={case}&tag={tag}&run={run}"
    if BROWSERS[tag] is None:
        start = f"{CR120} '{url}'"
    else:
        app, key = BROWSERS[tag]
        launch = json.dumps({"id": app, "params": {key: url}})
        start = f"luna-send -n 1 luna://com.webos.applicationManager/launch '{launch}' >/dev/null"
    fire(f"{CLOSE}sleep 4; pkill -9 -x browser; {start}")
    deadline = time.time() + CEILING[case]
    got = None
    while time.time() < deadline and not got:
        time.sleep(5)
        got = beacon(tag, case, run)
    fire(CLOSE)
    got = got or {"timeout": "1"}
    got.pop("ua", None)
    for k in ("tag", "case", "run"):
        got.pop(k, None)
    print(f"{tag} {case} #{run}: " + " ".join(f"{k}={v}" for k, v in got.items()), flush=True)


bench.tv("wget -q -O /dev/null http://127.0.0.1:8099/pages/harness.html || lighttpd -f /media/developer/bench/lighttpd.conf")
args = sys.argv[1:]
tags = ["stock", "ours"]
if args[0] == "-b":
    tags, args = args[1].split(","), args[2:]
stamp = int(time.time()) % 100000
for r in range(int(args[0])):
    for case in args[1:]:
        for tag in tags:
            run_one(tag, case, f"{stamp}-{r}")
