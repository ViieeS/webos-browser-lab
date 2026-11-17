#!/usr/bin/env python3
"""Flat CPU profile of our browser on the TV with perf: records the web process while a page loads
(or for N seconds of whatever it is doing), then names the samples on the Mac with addr2line on the
unstripped libWPEWebKit, because the TV perf has no libelf. Prints top functions per thread.
usage: perfsym.py <seconds, 0 = re-read the last recording> <unstripped lib, e.g. browser/build/lib-a55-p14v2-dbg.so> [url to launch first]
"""
import collections
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bench"))
import bench  # noqa: E402

seconds = int(sys.argv[1])
dbg = os.path.abspath(sys.argv[2])
url = sys.argv[3] if len(sys.argv) > 3 else None
PERF = "/media/developer/temp/perf"
LIBNAME = "libWPEWebKit-2.0.so.1"

local = os.path.join(ROOT, "build", "perf.txt.gz")
if seconds:   # 0 re-reads the last fetched recording
    record = (f"cd /tmp; rm -f /tmp/perf.data; for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do "
              f"pidof WPEWebProcess >/dev/null && break; sleep 0.2; done; "
              f"{PERF} record -F 499 -p $(pidof WPEWebProcess | tr ' ' ',') -o /tmp/perf.data sleep {seconds} >/dev/null 2>&1; "
              f"ls -la /tmp/perf.data")
    if url:
        close = "".join(f"luna-send -n 1 luna://com.webos.applicationManager/closeByAppId '{{\"id\":\"{a}\"}}' >/dev/null; "
                        for a in (bench.APP, *bench.BACKGROUND_APPS))
        launch = '{"id":"%s","params":{"url":"%s"}}' % (bench.APP, url)
        bench.tv(f"{close}sleep 3; pkill -9 -x browser; sleep 1")
        # A telnet session that launches an app may hang until tvtelnet gives up: launch apart, record apart.
        try:
            bench.tv(f"luna-send -n 1 luna://com.webos.applicationManager/launch '{launch}' >/dev/null", timeout=15)
        except subprocess.TimeoutExpired:
            pass
    print(bench.tv(record, timeout=seconds + 120).strip().splitlines()[-1:])
    bench.tv(f"cd /tmp; {PERF} script -i /tmp/perf.data --show-mmap-events -F comm,tid,ip,dso > /tmp/perf.txt 2>/dev/null; "
             f"gzip -f /tmp/perf.txt")
    subprocess.run(["python3", os.path.join(ROOT, "host", "tvfetch.py"), bench.TV,
                    "/tmp/perf.txt.gz", local], check=True, capture_output=True)
text = subprocess.run(["gunzip", "-c", local], capture_output=True, text=True).stdout

# mmap events give where the library's executable segment sits: ip - start + pgoff = file offset,
# which is the vaddr for a shared library's first (text) segment.
maps = []
for m in re.finditer(r"PERF_RECORD_MMAP2? \d+/\d+: \[(0x[0-9a-f]+)\((0x[0-9a-f]+)\) @ (0x[0-9a-f]+|\d+)[^\]]*\]: (?:[rwxps-]+ )?(\S+)", text):
    start, size, pgoff, path = int(m.group(1), 16), int(m.group(2), 16), int(m.group(3), 0), m.group(4)
    if path.endswith(LIBNAME):
        maps.append((start, start + size, pgoff))
samples = []   # (thread, where)
offsets = set()
for line in text.splitlines():
    m = re.match(r"\s*(\S.*?)\s+(\d+)\s+([0-9a-f]+)\s+\((\S+)\)", line)
    if not m:
        continue
    comm, ip, dso = m.group(1), int(m.group(3), 16), m.group(4)
    if dso.endswith(LIBNAME):
        for s, e, pg in maps:
            if s <= ip < e:
                off = ip - s + pg
                offsets.add(off)
                samples.append((comm, off))
                break
        else:
            samples.append((comm, "webkit?"))
    else:
        samples.append((comm, os.path.basename(dso)))

names = {}
if offsets:
    ordered = sorted(offsets)
    out = subprocess.run(["docker", "run", "--rm", "-i", "-v", "wpe-br:/work", "-v", f"{os.path.dirname(dbg)}:/d:ro", "wpe-br",
                          "/work/buildroot/output/host/bin/arm-webos-linux-gnueabi-addr2line", "-f", "-C",
                          "-e", f"/d/{os.path.basename(dbg)}"],
                         input="\n".join(hex(o) for o in ordered), capture_output=True, text=True).stdout.splitlines()
    for i, off in enumerate(ordered):
        names[off] = out[2 * i] if 2 * i < len(out) else "?"
by_thread = collections.defaultdict(collections.Counter)
for comm, where in samples:
    by_thread[comm][names.get(where, where) if isinstance(where, int) else where] += 1
total = len(samples)
print(f"{total} samples, {len(maps)} libWPEWebKit mappings")
for comm, c in sorted(by_thread.items(), key=lambda kv: -sum(kv[1].values()))[:4]:
    n = sum(c.values())
    print(f"== {comm}: {n} samples ({100 * n / total:.0f}%)")
    for name, k in c.most_common(25):
        print(f"  {100 * k / n:5.1f}%  {name[:150]}")

# Coarse buckets for the main web thread, by function name: where a load's time goes at a glance.
BUCKETS = [("style", r"SelectorChecker|SelectorFilter|ElementRuleCollector|Style::|RenderStyle|CSS|SelectorDataList|RuleSet|MatchedDeclarations"),
           ("layout", r"Layout::|RenderBlock|RenderBox|RenderFlex|RenderGrid|LineBuilder|RenderText|RenderLayer|LayoutContext|findNextLayer"),
           ("js", r"JSC::|llint|LLInt|perf-\\d+\\.map|Yarr"),
           ("dom", r"WebCore::(Element|Node|ContainerNode|Document|HTML|Attr|Text|CharacterData|Event)"),
           ("paint", r"GraphicsContext|Skia|Sk[A-Z]|Paint|Display::|harfbuzz|freetype|FontCascade|Glyph"),
           ("alloc", r"bmalloc|libc-2|malloc|free|libstdc"),
           ("gpu+kernel", r"libmali|kernel")]
main = by_thread.get("WPEWebProcess", collections.Counter())
n = sum(main.values()) or 1
bucket = collections.Counter()
for name, k in main.items():
    for label, rx in BUCKETS:
        if re.search(rx, str(name)):
            bucket[label] += k
            break
    else:
        bucket["other"] += k
print("== WPEWebProcess thread by bucket")
for label, k in bucket.most_common():
    print(f"  {100 * k / n:5.1f}%  {label}")
