#!/usr/bin/env python3
"""Where a wheel notch's latency goes in Chromium TV: a trace of one inputlat wheel sequence, split by EventLatency stage.
The EventLatency histograms give only the total (~200 ms per notch even on Wikipedia); the trace has the same
measurement as nested async slices: GenerationToRendererCompositor, RendererCompositor*, BeginImplFrame*, ...,
SubmitCompositorFrameToPresentationCompositorFrame and its sub-stages down to the swap.
Tracing costs CPU on the TV, so read the shares between stages, not the absolute totals.
usage: wheeltrace.py run <tag> <site> <out.json.gz>     (site from inputlat.SITES, a -wheel one)
       wheeltrace.py show <trace.json.gz>...
Needs what inputlat.py needs.
"""
import gzip
import json
import os
import sys
import time

# EventLatency is in "cc,benchmark,input,disabled-by-default-devtools.timeline.frame"; the old comma string form of
# Tracing.start enabled none of cc/viz on this build, the traceConfig list does.
CATEGORIES = ["input", "benchmark", "latencyInfo", "rail", "cc", "viz", "gpu", "toplevel", "input.scrolling",
              "disabled-by-default-devtools.timeline.frame"]


def run(tag, site, out):
    import bench
    import inputlat
    import uilat
    url, gap, tokens = inputlat.SITES[site]
    br = uilat.start(tag, url)
    try:
        inputlat.wait_ready(site)
        time.sleep(8)
        br.call("Tracing.start", {"transferMode": "ReturnAsStream", "traceConfig": {
            "recordMode": "recordAsMuchAsPossible", "includedCategories": CATEGORIES}})
        time.sleep(1)
        bench.tv(f"/media/developer/temp/evkeys {inputlat.WHEEL_DEV} {gap} {' '.join(tokens)}", timeout=120)
        time.sleep(3)
        raw = out + ".tmp"
        br.trace_to(raw)
        with open(raw, "rb") as f, gzip.open(out, "wb") as g:
            g.write(f.read())
        os.remove(raw)
        print(f"{tag} {site}: trace {os.path.getsize(out) // 1024} KB gz -> {out}", flush=True)
    finally:
        uilat.fire(uilat.close_all())


def stages(path):
    """{event type: {stage: [ms]}} from the EventLatency async slices. A stage slice shares the id of its
    EventLatency parent; nesting is by time inside the same id."""
    data = json.load(gzip.open(path))
    events = data["traceEvents"] if isinstance(data, dict) else data
    open_, spans = {}, []
    for e in events:
        if e.get("ph") not in ("b", "e") or "id2" not in e and "id" not in e:
            continue
        key = (e.get("cat"), str(e.get("id", e.get("id2"))), e["name"])
        if e["ph"] == "b":
            open_[key] = e
        elif key in open_:
            b = open_.pop(key)
            spans.append((key[1], e["name"], b["ts"], e["ts"], b.get("args", {})))
    by_id = {}
    for sid, name, t0, t1, args in spans:
        by_id.setdefault(sid, []).append((name, t0, t1, args))
    out = {}
    for sid, items in by_id.items():
        root = next((i for i in items if i[0] == "EventLatency"), None)
        if not root:
            continue
        data = root[3].get("data") or root[3].get("event_latency") or {}
        etype = str(data.get("event_type") or root[3].get("event_type") or "?")
        d = out.setdefault(etype, {})
        for name, t0, t1, _ in items:
            d.setdefault(name, []).append((t1 - t0) / 1000)
    return out


def show(paths):
    for p in paths:
        print(p)
        for etype, d in sorted(stages(p).items()):
            total = d.get("EventLatency", [])
            print(f"  {etype}: n={len(total)} total mean {sum(total) / max(len(total), 1):.1f} ms")
            for name, xs in sorted(d.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
                if name != "EventLatency":
                    print(f"    {sum(xs) / len(xs):8.1f} ms  n={len(xs):3}  {name}")


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(*sys.argv[2:5])
    else:
        show(sys.argv[2:])
