#!/usr/bin/env python3
"""Watches a harness run in the stock browser: every 30 s prints whether its renderer process is alive,
the CPU the browser used meanwhile, and stops at the run's beacon or after the limit.
usage: watch_stock.py <run id> [limit s, default 900]
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bench  # noqa: E402

run, limit = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 900
CMD = ("for p in $(pgrep -f com.webos.app.browser/chrome); do "
       "t=$(tr '\\0' ' ' < /proc/$p/cmdline | grep -o -- '--type=[a-z-]*'); "
       "set -- $(sed 's/.*) //' /proc/$p/stat); echo \"P ${t:-browser} $(( ${12} + ${13} ))\"; done; "
       f"grep 'beacon?tag=stock&case=speedometer&run={run}&' /tmp/bench-access.log | tail -n 1")
t0, last = time.time(), None
while time.time() - t0 < limit:
    out = bench.tv(CMD)
    procs = re.findall(r"^P (\S+) (\d+)", out, re.M)
    cpu = sum(int(j) for _, j in procs)
    kinds = ",".join(sorted({k for k, _ in procs}))
    beacon = re.search(r"GET /beacon\?(\S+) HTTP", out)
    print(f"{int(time.time() - t0)}s procs={kinds} cpu_s={(cpu - last) / 100 if last is not None else 0:.1f}", flush=True)
    if beacon:
        print("BEACON " + beacon.group(1), flush=True)
        break
    last = cpu
    time.sleep(30)
