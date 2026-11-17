#!/usr/bin/env python3
"""Open a URL in the inspected browser and wait for a CSS selector's text to hold a number, the way
bench.py's "probe" param does for our own host. For browsers we cannot inject scripts into
(the aarch64 MiniBrowser). Prints "PROBE <seconds> <text>" or "TIMEOUT".
usage: probe.py <url> <selector> [timeout s, default 1200] [tv ip:port, default $TV_HOST:9223]
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inspector import Inspector  # noqa: E402

url, selector = sys.argv[1], sys.argv[2]
limit = float(sys.argv[3]) if len(sys.argv) > 3 else 1200
insp = Inspector(sys.argv[4] if len(sys.argv) > 4 else os.environ["TV_HOST"] + ":9223")
if os.environ.get("BENCH_UA"):   # the 32-bit host sends desktop Safari's; sites serve by UA
    insp.send("Page.overrideUserAgent", {"value": os.environ["BENCH_UA"]})
insp.send("Runtime.evaluate", {"expression": f"location.href = {json.dumps(url)}"})
t0 = time.time()
expr = f"(document.querySelector({json.dumps(selector)}) || {{}}).textContent || ''"
while time.time() - t0 < limit:
    ask = insp.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
    for msg in insp.messages(time.time() + 10):
        if msg.get("id") == ask:
            text = str(msg.get("result", {}).get("result", {}).get("value", "")).strip()
            if re.search(r"\d", text):
                print(f"PROBE {round(time.time() - t0)} {text}")
                sys.exit(0)
            break
print("TIMEOUT")
sys.exit(1)
