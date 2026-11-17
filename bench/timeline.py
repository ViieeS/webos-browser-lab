#!/usr/bin/env python3
"""Main-thread breakdown of a page load on the TV from Web Inspector's Timeline.

The browser must run with WEBKIT_INSPECTOR_HTTP_SERVER=<tv ip>:<port> and
WEBKIT_INSPECTOR_RESOURCES_PATH=<dir with inspector.gresource> (see inspector.py). Starts the Timeline,
navigates to the URL, records for N seconds, then prints self time per record type (time in a record
minus its children) and the scripts that took the most.
usage: timeline.py <url> [seconds, default 20] [tv ip:port, default $TV_HOST:9222]
"""
import collections
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inspector import Inspector  # noqa: E402

url = sys.argv[1]
seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 20
hostport = sys.argv[3] if len(sys.argv) > 3 else os.environ["TV_HOST"] + ":9222"
insp = Inspector(hostport)


def start_recording():
    insp.send("Inspector.enable")
    insp.send("Timeline.enable")
    insp.send("Page.enable")   # starts the stopwatch every Timeline timestamp is read from
    insp.send("Timeline.setInstruments", {"instruments": ["Timeline"]})
    insp.send("Timeline.start", {"maxCallStackDepth": 0})


records = []
start_recording()
if os.environ.get("BENCH_UA"):   # the 32-bit host sends desktop Safari's; sites serve by UA
    insp.send("Page.overrideUserAgent", {"value": os.environ["BENCH_UA"]})
if url != "-":   # "-" records the current page as it is (e.g. while the host's autoscroll runs)
    insp.send("Runtime.evaluate", {"expression": f"location.href = {json.dumps(url)}"})
for msg in insp.messages(time.time() + seconds):
    if msg.get("method") == "_newTarget":   # a cross-site navigation commits in a new page target
        start_recording()
    elif msg.get("method") == "Timeline.eventRecorded":
        records.append(msg["params"]["record"])
    elif "error" in msg and "already enabled" not in msg["error"].get("message", ""):
        print("error:", msg["error"], file=sys.stderr)
insp.send("Timeline.stop")

self_ms = collections.Counter()
count = collections.Counter()
scripts = collections.Counter()


def walk(r):
    dur = max(0.0, (r.get("endTime") or r.get("startTime", 0)) - r.get("startTime", 0)) * 1000
    kids = r.get("children") or []
    child = sum(max(0.0, (c.get("endTime") or c.get("startTime", 0)) - c.get("startTime", 0)) * 1000 for c in kids)
    t = r.get("type", "?")
    self_ms[t] += max(0.0, dur - child)
    count[t] += 1
    if t in ("EvaluateScript", "FunctionCall", "TimerFire", "EventDispatch", "ObserverCallback") and dur > 0:
        d = r.get("data") or {}
        key = f"{t} {d.get('url') or d.get('scriptName') or d.get('type') or ''}"[:110]
        scripts[key] += dur
    for c in kids:
        walk(c)


for r in records:
    walk(r)

# DUMP=<record type> prints a few such records with their parents' types and data: who triggers them.
if os.environ.get("DUMP"):
    shown = 0

    def dump(r, parents):
        global shown
        if r.get("type") == os.environ["DUMP"] and shown < 6:
            shown += 1
            print("DUMP", " > ".join(parents), "|", json.dumps(r.get("data"))[:300], file=sys.stderr)
        for c in r.get("children") or []:
            dump(c, parents + [r.get("type", "?")])

    for r in records[len(records) // 2:]:
        dump(r, [])
total = sum(self_ms.values())
print(f"records={len(records)} recorded_s={seconds} self_total_ms={total:.0f}")
for t, ms in self_ms.most_common(20):
    print(f"{ms:9.0f} ms {100 * ms / total if total else 0:5.1f}%  {count[t]:6}  {t}")
print("-- heaviest script entries (inclusive ms)")
for k, ms in scripts.most_common(15):
    print(f"{ms:9.0f}  {k}")
