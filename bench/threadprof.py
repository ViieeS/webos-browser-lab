#!/usr/bin/env python3
"""CPU per browser thread during a page's cold load and then a wheel scroll, from /proc on the TV.
Answers "which thread is the bottleneck" before reaching for a profiler.
usage: threadprof.py <url> [load seconds, default 15] [scroll seconds, default 12]
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bench  # noqa: E402

url = sys.argv[1]
load_s = int(sys.argv[2]) if len(sys.argv) > 2 else 15
scroll_s = int(sys.argv[3]) if len(sys.argv) > 3 else 12
T = "/media/developer/temp/threads.sh"
close = "".join(f"luna-send -n 1 luna://com.webos.applicationManager/closeByAppId '{{\"id\":\"{a}\"}}' >/dev/null; "
                for a in (bench.APP, *bench.BACKGROUND_APPS))
bench.tv(close + "sleep 3")
launch = json.dumps({"id": bench.APP, "params": {"url": url, "autoscroll": "wheel"}})
bench.tv(f": > {bench.LOG}; luna-send -n 1 luna://com.webos.applicationManager/launch '{launch}' >/dev/null; sleep 1; {T} snap A")
time.sleep(load_s)
bench.tv(f"{T} snap B")
time.sleep(scroll_s)
out = bench.tv(f"{T} snap C; echo == load {load_s}s; {T} diff A B; echo == scroll {scroll_s}s; {T} diff B C; "
               f"grep -E '^LOAD|SCROLL|CRASH' {bench.LOG}")
print(out)
bench.tv(f"luna-send -n 1 luna://com.webos.applicationManager/closeByAppId '{{\"id\":\"{bench.APP}\"}}' >/dev/null")
