#!/usr/bin/env python3
"""Main-thread Timeline while the host scrolls a page with the wheel: launches our browser with the
inspector, starts the wheel 6 s after load, records 9 s of it, then prints the Timeline summary, the
repainted rects and the frames the screen got. Answers "what does the main thread do per scroll frame".
usage: wheeltl.py <url> [installed lib suffix to switch to first, e.g. a55v2]
"""
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bench  # noqa: E402

url = sys.argv[1]
lib = sys.argv[2] if len(sys.argv) > 2 else None
L = f"{bench.APPDIR}/lib"
env = f"WEBKIT_INSPECTOR_HTTP_SERVER={bench.TV}:9222,WEBKIT_INSPECTOR_RESOURCES_PATH=/media/developer/temp/inspector"
launch = ('{"id":"%s","params":{"url":"%s","autoscroll":"wheel","wheeldelay":"6000","env":"%s"}}'
          % (bench.APP, url, env))
close = "".join(f"luna-send -n 1 luna://com.webos.applicationManager/closeByAppId '{{\"id\":\"{a}\"}}' >/dev/null; "
                for a in (bench.APP, *bench.BACKGROUND_APPS))
swap = f"cp {L}/libWPEWebKit.{lib} {L}/libWPEWebKit-2.0.so.1; " if lib else ""
bench.tv(f"{close}sleep 3; pkill -9 -x browser; {swap}md5sum {L}/libWPEWebKit-2.0.so.1; : > {bench.LOG}; "
         f"luna-send -n 1 luna://com.webos.applicationManager/launch '{launch}' >/dev/null")
deadline = time.time() + 40
while time.time() < deadline and "LOAD" not in bench.tv(f"grep -c '^LOAD' {bench.LOG} | grep -v '^0' && echo LOAD"):
    time.sleep(1)
time.sleep(5)
tl = subprocess.run(["python3", os.path.join(os.path.dirname(os.path.abspath(__file__)), "timeline.py"), "-", "9",
                     f"{bench.TV}:9222"], capture_output=True, text=True, env={**os.environ, "DUMP": "Paint"})
print("\n".join(l for l in tl.stdout.splitlines()[:8]))
clips = re.findall(r'"clip": \[([^\]]*)\]', tl.stderr)
print("repainted rects (of 6 sampled):", sorted(set(clips)))
time.sleep(3)
out = bench.tv(f"grep -E '^(PRESENT|SCROLL)' {bench.LOG}")
frames = [int(m) for m in re.findall(r"PRESENT frames=(\d+)", out)]
print("PRESENT frames per period (last 10):", frames[-10:])
bench.tv(close)
