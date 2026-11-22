#!/usr/bin/env python3
"""Where the CPU goes while Chromium TV scrolls: system-wide perf on the TV during a steady wheel scroll, plus CPU
time per thread. Answers "which stage runs at 40 ms" for the late scroll frames (cr151/INPUT_LATENCY.md).

record: launches the app on the page (uilat.start, fresh process), waits, then in one telnet session takes a
  threads_cr151.sh snapshot, starts `perf record -a`, sends NOTCHES wheel notches through evkeys (event3), and takes
  a second snapshot. perf script output (comm, pid, tid, ip, dso, mmap events) comes back gzipped.
report: names the chrome samples with llvm-symbolizer on the unstripped chrome in the cr151work volume (the
  installed chrome must be its stripped copy: same md5 as /work/dist/browser/chrome). Prints samples per process
  and thread, then the top functions of the busiest threads.
Needs TV_HOST, tcprelay <TV LAN ip> 9226 -> 9225, evkeys, keepawake.sh, perf in /media/developer/temp.
usage: scrollperf.py record <out.txt.gz> [variant] [url]     scrollperf.py report <out.txt.gz> [threads]
"""
import collections
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bench  # noqa: E402
import uilat  # noqa: E402
from inputlat import CENTER, WHEEL_DEV  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PERF = "/media/developer/temp/perf"
THREADS = "sh /media/developer/temp/threads_cr151.sh"
URL = "https://en.wikipedia.org/wiki/Television"
NOTCHES, GAP_MS, SECONDS = 60, 80, 7   # 60 notches 80 ms apart = 4.8 s of scrolling inside a 7 s recording
CHROME = "/work/c151/src/out/tv/chrome"


def record(out, variant, url):
    uilat.start(f"chromiumtv+{variant}" if variant else "chromiumtv", url).ws.sock.close()
    time.sleep(5)
    # A long telnet command line resets the session, so the steps go into a script, one short line per call.
    script = [
        "cd /tmp; rm -f perf.data perf.txt perf.txt.gz",
        f"N=''; i=0; while [ $i -lt {NOTCHES} ]; do N=\"$N r8:-1\"; i=$((i+1)); done",
        f"{THREADS} snap A",
        "for p in $(pidof chrome); do echo PROC $p $(tr '\\0' ' ' < /proc/$p/cmdline | grep -o -- '--type=[a-z-]*'); done > procs.txt",
        f"{PERF} record -a -F 999 -o /tmp/perf.data sleep {SECONDS} >/dev/null 2>&1 &",
        "sleep 0.5",
        f"/media/developer/temp/evkeys {WHEEL_DEV} {GAP_MS} {CENTER} $N",
        "wait",
        f"{THREADS} snap B",
        f"{PERF} script -i perf.data --show-mmap-events -F comm,pid,tid,ip,dso > perf.txt 2>/dev/null",
        f"{{ cat procs.txt; {THREADS} diff A B | sed 's/^/CPU /'; cat perf.txt; }} | gzip > perf.txt.gz",
        "ls -la perf.txt.gz",
    ]
    bench.tv(": > /tmp/scrollperf.sh")
    for line in script:
        quoted = line.replace("'", "'\\''")
        bench.tv(f"printf '%s\\n' '{quoted}' >> /tmp/scrollperf.sh")
    print(bench.tv("sh /tmp/scrollperf.sh", timeout=SECONDS + 200).strip().splitlines()[-1:], flush=True)
    subprocess.run(["python3", os.path.join(ROOT, "host", "tvfetch.py"), bench.TV, "/tmp/perf.txt.gz", out],
                   check=True, capture_output=True)
    uilat.fire(uilat.close_all())


def segments():
    """(p_offset, p_vaddr, p_filesz) of chrome's executable LOAD segments, to turn file offsets into addresses."""
    text = subprocess.run(["docker", "run", "--rm", "-v", "cr151work:/work", "cr151", "/usr/lib/llvm-23/bin/llvm-readelf", "-lW", CHROME],
                          capture_output=True, text=True, check=True).stdout
    segs = []
    for m in re.finditer(r"^\s*LOAD\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+0x[0-9a-f]+\s+(0x[0-9a-f]+)\s+0x[0-9a-f]+\s+(\S+ ?\S*)",
                         text, re.M):
        if "E" in m.group(4):
            segs.append((int(m.group(1), 16), int(m.group(2), 16), int(m.group(3), 16)))
    return segs


def symbolize(addrs):
    out = subprocess.run(["docker", "run", "--rm", "-i", "-v", "cr151work:/work", "cr151", "/usr/lib/llvm-23/bin/llvm-symbolizer",
                          f"--obj={CHROME}", "--functions=linkage", "--no-inlines", "--demangle", "--output-style=JSON"],
                         input="\n".join(hex(a) for a in addrs), capture_output=True, text=True, check=True).stdout
    names = {}
    for line in out.splitlines():
        r = json.loads(line)
        sym = (r.get("Symbol") or [{}])[0].get("FunctionName", "?")
        names[int(r["Address"], 16)] = re.sub(r"\(.*", "", sym)[:140]
    return names


def report(path, top_threads):
    text = subprocess.run(["gunzip", "-c", path], capture_output=True, text=True, check=True).stdout
    ptype = {m.group(1): (m.group(2) or "--type=browser")[7:] for m in re.finditer(r"^PROC (\d+) ?(\S*)", text, re.M)}
    cpu = [line[4:] for line in text.splitlines() if line.startswith("CPU ")]
    maps = collections.defaultdict(list)   # pid -> (start, end, pgoff) of chrome's mappings
    for m in re.finditer(r"(\d+)/\d+: \[(0x[0-9a-f]+)\((0x[0-9a-f]+)\) @ (0x[0-9a-f]+|\d+)[^\]]*\]: (?:[rwxps-]+ )?(\S+)", text):
        if m.group(5).endswith("/chrome"):
            s = int(m.group(2), 16)
            maps[m.group(1)].append((s, s + int(m.group(3), 16), int(m.group(4), 0)))
    segs = segments()
    samples, addrs = [], set()
    for line in text.splitlines():
        m = re.match(r"\s*(\S.*?)\s+(\d+)/(\d+)\s+([0-9a-f]+)\s+\((\S+)\)", line)
        if not m:
            continue
        comm, pid, ip, dso = m.group(1), m.group(2), int(m.group(4), 16), m.group(5)
        proc = f"chrome:{ptype[pid]}" if pid in ptype else None
        where = os.path.basename(dso)
        if dso.endswith("/chrome"):
            where = "chrome?"
            for s, e, pg in maps.get(pid, ()):
                if s <= ip < e:
                    off = ip - s + pg
                    for po, pv, fs in segs:
                        if po <= off < po + fs:
                            where = off - po + pv
                            addrs.add(where)
                    break
        samples.append((proc or comm.split("/")[0] + f"[{pid}]", comm, where))
    names = symbolize(sorted(addrs)) if addrs else {}
    total = len(samples)
    print(f"{total} samples (999 Hz x 4 CPUs x {SECONDS} s = {999 * 4 * SECONDS} max)")
    idle = sum(1 for p, c, w in samples if c == "swapper")
    print(f"idle (swapper): {100 * idle / total:.0f} %")
    by_proc = collections.Counter(p for p, c, w in samples if c != "swapper")
    print("== by process (non-idle)")
    for p, k in by_proc.most_common(12):
        print(f"  {100 * k / total:5.1f}%  {p}")
    by_thread = collections.defaultdict(collections.Counter)
    for p, c, w in samples:
        if c != "swapper":
            by_thread[(p, c)][names.get(w, w) if isinstance(w, int) else w] += 1
    print("== by thread")
    ranked = sorted(by_thread.items(), key=lambda kv: -sum(kv[1].values()))
    for (p, c), cnt in ranked[:20]:
        print(f"  {100 * sum(cnt.values()) / total:5.1f}%  {p} / {c}")
    for (p, c), cnt in ranked[:top_threads]:
        n = sum(cnt.values())
        print(f"== {p} / {c}: {n} samples")
        for name, k in cnt.most_common(20):
            print(f"  {100 * k / n:5.1f}%  {name}")
    print("== CPU jiffies per thread over the recording (threads_cr151.sh)")
    for line in cpu[:15]:
        print("  " + line)


if __name__ == "__main__":
    if sys.argv[1] == "record":
        record(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "-" else "",
               sys.argv[4] if len(sys.argv) > 4 else URL)
    else:
        report(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 6)
