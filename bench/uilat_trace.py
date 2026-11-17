#!/usr/bin/env python3
"""Stage split of Chromium's own latency slices in a JSON trace from `uilat.py trace`.
EventLatency (one per input event) and PipelineReporter (one per frame) are async slices whose nested slices with the
same id are Chromium's stages. Prints, per stage path, how many slices have it and the median and p90 duration in ms.
usage: uilat_trace.py <trace.json> [EventLatency|PipelineReporter] [event_type, default KEY_PRESSED]
PipelineReporter is split per process (browser UI compositor vs renderer), the pid is in the path.
"""
import collections
import json
import statistics
import sys

path = sys.argv[1]
root_name = sys.argv[2] if len(sys.argv) > 2 else "EventLatency"
event_type = sys.argv[3] if len(sys.argv) > 3 else "KEY_PRESSED"
d = json.load(open(path))
events = d["traceEvents"] if isinstance(d, dict) else d
by_id = collections.defaultdict(list)   # (pid, cat, id) -> async begin/end events in time order
for e in events:
    if e.get("ph") in ("b", "e") and "id2" in e:
        key = (e["pid"], e["cat"], e["id2"].get("local") or e["id2"].get("global"))
        by_id[key].append(e)

stages = collections.defaultdict(list)   # stage path -> [ms]
roots = 0
for (pid, _, _), evs in by_id.items():
    evs.sort(key=lambda e: e["ts"])
    stack = []   # (name, ts, path)
    in_root = False
    for e in evs:
        if e["ph"] == "b":
            if not stack:
                if e["name"] != root_name:
                    continue
                args = e.get("args", {}).get("event_latency", {})
                in_root = root_name != "EventLatency" or args.get("event_type") == event_type
                prefix = f"{root_name}[{pid}]" if root_name == "PipelineReporter" else root_name
                stack.append((e["name"], e["ts"], prefix))
                continue
            stack.append((e["name"], e["ts"], f"{stack[-1][2]} > {e['name']}"))
        elif stack:
            name, ts, p = stack.pop()
            if in_root:
                stages[p].append((e["ts"] - ts) / 1000)
                if not stack:
                    roots += 1
print(f"{roots} {root_name} slices" + (f" ({event_type})" if root_name == "EventLatency" else ""))
total = len(stages.get(root_name, [])) or roots
for p in sorted(stages):
    v = sorted(stages[p])
    p90 = v[int(0.9 * (len(v) - 1))]
    print(f"{len(v):5d}  median {statistics.median(v):7.1f}  p90 {p90:7.1f}  {p}")
