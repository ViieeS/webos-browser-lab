#!/usr/bin/env python3
"""Cold-load milestones of a page in any inspected browser on the TV (our 32-bit host on :9222, the
aarch64 MiniBrowser on :9223), from the page's own Navigation/Paint Timing, so both builds are
measured the same way. Opens about:blank first so the measured navigation is a fresh one.
usage: navtime.py <url> [wait s, default 35] [tv ip:port, default $TV_HOST:9223] [selector to count]
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inspector import Inspector  # noqa: E402

url = sys.argv[1]
wait = float(sys.argv[2]) if len(sys.argv) > 2 else 35
hostport = sys.argv[3] if len(sys.argv) > 3 else os.environ["TV_HOST"] + ":9223"
count = sys.argv[4] if len(sys.argv) > 4 else "ytd-rich-item-renderer"
insp = Inspector(hostport)
insp.send("Runtime.evaluate", {"expression": f"location.href = {json.dumps(url)}"})
for _ in insp.messages(time.time() + wait):
    pass
expr = ("JSON.stringify({nav: (n => n ? {dcl: Math.round(n.domContentLoadedEventEnd), load: Math.round(n.loadEventEnd)} : null)"
        "(performance.getEntriesByType('navigation')[0]),"
        " fcp: (performance.getEntriesByType('paint').find(p => p.name === 'first-contentful-paint') || {}).startTime | 0,"
        f" count: document.querySelectorAll({json.dumps(count)}).length, url: location.href.slice(0, 60)}})")
# A fresh connection: after the cross-site switch the first one does not always get the reply, and
# the server serves one client at a time, so the first one is closed before.
insp.ws.sock.close()
insp = Inspector(hostport)
ask = insp.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
for msg in insp.messages(time.time() + 20):
    if msg.get("id") == ask:
        print("NAVTIME", msg.get("result", {}).get("result", {}).get("value", msg))
        break
