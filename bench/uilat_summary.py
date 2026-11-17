#!/usr/bin/env python3
"""Summarises uilat.py output: per build and metric, the event-weighted mean over all runs, the range of per-run
means, and the range of per-run medians (bucket lower bounds). EventLatency is in microseconds, printed as ms.
usage: uilat_summary.py <uilat output file>
"""
import collections
import re
import sys

ITEM = re.compile(r"\s*(\S+) n=(\d+) mean=([\d.]+) p50>=(\d+)")
SHOWN = ("Omnibox.CharTypedToRepaintLatency", "Omnibox.Views.PopupFirstPaint", "Browser.Tabs.TotalSwitchDuration3",
         "EventLatency.KeyPressed.TotalLatency", "Startup.BrowserWindowDisplay", "Startup.BrowserWindow.FirstPaint",
         "Startup.FirstWebContents.NonEmptyPaint3")
runs = collections.defaultdict(list)   # (metric, scenario, build) -> [(n, mean, p50)]
for line in open(sys.argv[1]):
    head, _, body = line.partition(": ")
    build, scenario = head.split()[:2]
    if "startup" in head:
        scenario = "startup"
    for item in body.split(";"):
        m = ITEM.match(item)
        if not m or not m.group(1).startswith(SHOWN) or ".WithSavedFrames" in m.group(1):
            continue
        name, n, mean, p50 = m.group(1), int(m.group(2)), float(m.group(3)), int(m.group(4))
        if name.startswith("Startup.") != (scenario == "startup"):
            continue
        scale = 1000 if name.startswith("EventLatency") else 1
        runs[(name, scenario, build)].append((n, mean / scale, p50 / scale))
builds = sorted({k[2] for k in runs}, reverse=True)
print("| Metric | Scenario | " + " | ".join(builds) + " |")
print("|---|---|" + "---|" * len(builds))
for name, scenario in sorted({k[:2] for k in runs}, key=lambda k: (k[1] == "startup", k)):
    cells = []
    for b in builds:
        r = runs.get((name, scenario, b), [])
        if not r:
            cells.append("—")
            continue
        n = sum(x[0] for x in r)
        mean = sum(x[0] * x[1] for x in r) / n
        cells.append(f"{mean:.0f} ms (runs {min(x[1] for x in r):.0f}-{max(x[1] for x in r):.0f}, "
                     f"p50 {min(x[2] for x in r):.0f}-{max(x[2] for x in r):.0f}, n={n})")
    print(f"| {name} | {scenario} | " + " | ".join(cells) + " |")
