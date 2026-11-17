#!/usr/bin/env python3
"""A/B bench for the browser on the TV.

Every case is one fresh browser launch with launch params; the host and the pages log
"LOAD <ms>", "BENCH ...", "SCROLL ...", "PRESENT ...", "PROBE <s> <score>", "MATHFOLD ...", "CRASH ..."
lines, which become one JSON record per run in results/<label>.jsonl with the build fingerprint.

Local cases (@local) load from lighttpd on the TV (127.0.0.1:8099, browser/bench/lighttpd.conf), so
the network stays out of the numbers. Net cases (@net) load real sites and are noisier.

  bench.py run --label L [--repeat N] [--p key=value ...] [case | @local | @net | @all ...]
  bench.py compare A B [case ...]      medians, spread, delta, permutation p-value
  bench.py show L
"""
import argparse
import itertools
import json
import os
import random
import re
import statistics
import subprocess
import sys
import time

TV = os.environ["TV_HOST"]   # the rooted TV, telnet root without login
TVTELNET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tvtelnet.py")
APP = "com.viiees.browser"
APPDIR = f"/media/developer/apps/usr/palm/applications/{APP}"
LOG = f"/var/palm/jail/{APP}/tmp/browser.log"
HTTP = "http://127.0.0.1:8099"
# webOS preloads these in the background, and again after a memory-pressure event; closed before every
# case so free memory does not depend on whether they happen to be loaded (~140 MB together).
BACKGROUND_APPS = ("youtube.leanback.v4", "com.webos.app.browser")
BOOT = None   # TV boot time (btime) at the start of the run
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
WIKI_LOCAL = f"{HTTP}/pages/wiki/en.wikipedia.org/wiki/Television.html"
WIKI = "https://en.wikipedia.org/wiki/Television"

# name -> (kind, launch params, ceiling in seconds). Probe cases are polled until the score shows.
CASES = {
    "micro":          ("local", {"url": f"file://{APPDIR}/bench.html"}, 25),
    "mathfold":       ("local", {"url": f"{HTTP}/pages/mathfold.html"}, 45),
    "speedometer":    ("local", {"url": f"{HTTP}/speedometer3.1/index.html?startAutomatically&iterationCount=2",
                                 "probe": "#result-number"}, 1200),
    "jetstream-js":   ("local", {"url": f"{HTTP}/jetstream3.0/index.html?startAutomatically&tag=js",
                                 "probe": "#result-summary .score",
                                 "watch": ".benchmark-running .benchmark-name"}, 3000),
    "motionmark":     ("local", {"url": f"{HTTP}/motionmark1.3.2/MotionMark/index.html",
                                 "click": "#start-button", "probe": "#results .score"}, 1500),
    "load-wiki":      ("local", {"url": WIKI_LOCAL}, 20),
    "wheel-wiki":     ("local", {"url": WIKI_LOCAL, "autoscroll": "wheel"}, 25),
    "wheel-wiki-settled": ("local", {"url": WIKI_LOCAL, "autoscroll": "wheel", "wheeldelay": "10000"}, 35),
    "raf-wiki":       ("local", {"url": WIKI_LOCAL, "autoscroll": "1"}, 30),
    "cold-google":    ("net", {"url": "https://www.google.com"}, 30),
    "cold-wiki":      ("net", {"url": WIKI}, 30),
    "cold-youtube":   ("net", {"url": "https://www.youtube.com"}, 40),
    "nav-google-wiki": ("net", {"url": "https://www.google.com", "then": WIKI}, 40),
    "wheel-youtube":  ("net", {"url": "https://www.youtube.com", "autoscroll": "wheel"}, 35),
    # The same scroll 30 s after load: YouTube keeps the main thread busy for ~20 s after load, so
    # wheel-youtube measures scrolling during start-up and this one a settled page.
    "wheel-youtube-settled": ("net", {"url": "https://www.youtube.com", "autoscroll": "wheel",
                                      "wheeldelay": "30000"}, 60),
}
# Metrics where a bigger number is better; everything else (ms, crashes, bad) wants smaller.
HIGHER_IS_BETTER = {"score", "screen_fps", "raf_fps"}
REPORT = (f"grep -E '^START|^LOAD|BENCH|SCROLL|^PRESENT|^CRASH|PROBE|MATHFOLD done' {LOG}; "
          "echo RSS $(ps -eo rss,comm | grep WPEWebProcess | sort -rn | head -1 | awk '{print $1}'); "
          "echo PROCS $(ps -eo comm | grep -c WPEWebProcess); grep btime /proc/stat")


def tv(cmd, timeout=240):
    return subprocess.run(["python3", TVTELNET, TV, cmd], capture_output=True, text=True, timeout=timeout).stdout


def fingerprint():
    out = tv(f"md5sum {APPDIR}/lib/libWPEWebKit-2.0.so.1 {APPDIR}/browser; "
             f"grep MemAvailable /proc/meminfo; grep btime /proc/stat; "
             f"wget -q -O /dev/null {HTTP}/pages/mathfold.html || lighttpd -f /media/developer/bench/lighttpd.conf")
    sums = re.findall(r"^([0-9a-f]{32})\s", out, re.M)
    avail = re.search(r"MemAvailable:\s+(\d+)", out)
    global BOOT
    BOOT = re.search(r"^btime (\d+)", out, re.M).group(1)
    return {"lib_md5": sums[0][:12] if sums else "?", "host_md5": sums[1][:12] if len(sums) > 1 else "?",
            "avail_kb_before": int(avail.group(1)) if avail else None}


def parse(out):
    lines = [l.split("CONSOLE LOG ")[-1].strip() for l in out.splitlines() if l.strip()]
    m = {}
    # A LOAD with no URI is the initial empty document, not a page.
    loads = [int(l.split()[1]) for l in lines if l.startswith("LOAD ") and len(l.split()) > 2]
    if loads:
        m["load_ms"] = loads[0]
    if len(loads) > 1 and not any(l.startswith("CRASH") for l in lines):
        m["load2_ms"] = loads[1]
    for l in lines:
        if l.startswith("BENCH total"):
            m["micro_total_ms"] = int(l.split()[2])
        elif l.startswith("SCROLL fps="):
            m["raf_fps"] = float(re.search(r"fps=([\d.]+)", l).group(1))
        elif l.startswith("PROBE "):
            m["probe_s"], m["score"] = int(l.split()[1]), float(re.search(r"[\d.]+", l.split(None, 2)[2]).group())
        elif l.startswith("MATHFOLD done"):
            m["mathfold_bad"] = int(re.search(r"bad=(\d+)", l).group(1))
        elif l.startswith("RSS ") and l.split()[1:]:
            m["rss_kb"] = int(l.split()[1])
        elif l.startswith("PROCS "):
            m["webprocs"] = int(l.split()[1])
    m["crashes"] = sum(l.startswith("CRASH") for l in lines)
    # A second START means the whole app died (memchute under memory pressure) and
    # surface-manager relaunched it without params; the numbers after it are not this case's.
    starts = sum(l.startswith("START ") for l in lines)
    if starts > 1:
        m["killed"] = starts - 1
    scroll_at = next((i for i, l in enumerate(lines) if l.startswith("SCROLL")), None)
    if scroll_at is not None:
        shown = [int(l.split("frames=")[1].split()[0]) for l in lines[max(0, scroll_at - 8):scroll_at]
                 if l.startswith("PRESENT")]
        if shown:
            m["screen_fps"] = round(sum(shown) / len(shown), 1)
    return m


def run_case(name, extra):
    kind, params, ceiling = CASES[name]
    params = {**params, **extra}
    launch = json.dumps({"id": APP, "params": params})
    close = "".join(f"luna-send -n 1 luna://com.webos.applicationManager/closeByAppId '{{\"id\":\"{app}\"}}' >/dev/null; "
                    for app in (APP, *BACKGROUND_APPS))
    # closeByAppId returns before the host exits; a launch that lands in the dying instance is
    # swallowed and the case reads the previous case's log. Wait for the exit, then make sure.
    gone = "for i in 1 2 3 4 5 6 7 8 9 10; do pidof browser >/dev/null || break; sleep 1; done; pkill -9 -x browser; "
    start = (f"{close}{gone}sleep 2; : > {LOG}; luna-send -n 1 luna://com.webos.applicationManager/launch '{launch}' >/dev/null")
    t0 = time.time()
    if "probe" not in params:
        # Separate short sessions: a telnet session that launches the app and then sleeps sometimes
        # never delivers its end marker, and tvtelnet returns a cut transcript after 180 s.
        tv(start)
        time.sleep(ceiling)
        out = tv(REPORT)
        if "PROCS " not in out:
            out = tv(REPORT)   # tvtelnet returns a cut or empty transcript silently; the log is still there
    else:
        tv(start)   # tvtelnet gives up after 180 s, so long suites are polled from here
        peak = 0
        while True:
            time.sleep(20)
            out = tv(REPORT)
            peak = max([peak] + [int(x) for x in re.findall(r"^RSS (\d+)", out, re.M)])
            if "PROBE" in out or "CRASH" in out or out.count("START ") > 1 or time.time() - t0 > ceiling:
                break
    tv(f"luna-send -n 1 luna://com.webos.applicationManager/closeByAppId '{{\"id\":\"{APP}\"}}' >/dev/null")
    boot = re.search(r"^btime (\d+)", out, re.M)
    if boot and boot.group(1) != BOOT:
        # A reboot mid-run silently turns every later case into an empty or cold-start record.
        raise SystemExit(f"{name}: the TV rebooted during the run (boot time {BOOT} -> {boot.group(1)})")
    m = parse(out)
    first = next((l.split()[2] for l in out.splitlines() if l.startswith("LOAD ") and len(l.split()) > 2), None)
    if kind == "local" and first and first != params["url"]:
        print(f"{name}: loaded {first}, expected {params['url']}", file=sys.stderr, flush=True)
        m["wrong_page"] = 1
    if "PROCS " not in out:
        # No report at all must not pass for a run that measured nothing.
        print(f"{name}: no report from the TV", file=sys.stderr, flush=True)
        m["no_report"] = 1
    if "probe" in params and peak:
        m["peak_rss_kb"] = peak
    if params.get("autoscroll") != "wheel":
        # With JS-driven scrolling the compositor re-presents unchanged frames, so the screen rate
        # says nothing; raf_fps is that case's number.
        m.pop("screen_fps", None)
    if "probe" in params and "score" not in m and not m["crashes"] and "killed" not in m:
        m["timeout"] = 1
    return m


def expand(names):
    out = []
    for n in names or ["@local"]:
        if n.startswith("@"):
            out += [c for c, (kind, _, _) in CASES.items() if n == "@all" or kind == n[1:]]
        else:
            out.append(n)
    return out


def load(label):
    with open(os.path.join(RESULTS, f"{label}.jsonl")) as f:
        return [json.loads(l) for l in f if l.strip()]


def cmd_run(a):
    os.makedirs(RESULTS, exist_ok=True)
    extra = dict(p.split("=", 1) for p in a.p)
    cases = expand(a.cases)
    meta = fingerprint()
    path = os.path.join(RESULTS, f"{a.label}.jsonl")
    for it, name in itertools.product(range(a.repeat), cases):
        m = run_case(name, extra)
        rec = {"label": a.label, "case": name, "iter": it, "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
               "params": extra, **meta, "metrics": m}
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"{name} #{it}: " + " ".join(f"{k}={v}" for k, v in m.items()), flush=True)


def summarize(records):
    by = {}
    for r in records:
        for k, v in r["metrics"].items():
            by.setdefault((r["case"], k), []).append(v)
    return by


def perm_p(a, b, rounds=4000):
    """Two-sided permutation test on the difference of medians; exact enough for n <= 10 per side."""
    if len(a) < 2 or len(b) < 2:
        return None
    obs = abs(statistics.median(a) - statistics.median(b))
    pool, n, hits = a + b, len(a), 0
    rnd = random.Random(1)
    for _ in range(rounds):
        rnd.shuffle(pool)
        if abs(statistics.median(pool[:n]) - statistics.median(pool[n:])) >= obs - 1e-12:
            hits += 1
    return hits / rounds


def fmt(vals):
    return f"{statistics.median(vals):g} [{min(vals):g}..{max(vals):g}] n={len(vals)}"


def cmd_show(a):
    for (case, k), vals in sorted(summarize(load(a.label)).items()):
        print(f"{case:16} {k:15} {fmt(vals)}")


def cmd_compare(a):
    sa, sb = summarize(load(a.a)), summarize(load(a.b))
    print(f"{'case':16} {'metric':15} {a.a:>30} {a.b:>30}  delta   p")
    for key in sorted(set(sa) | set(sb)):
        case, k = key
        if a.cases and case not in a.cases:
            continue
        va, vb = sa.get(key, []), sb.get(key, [])
        if not va or not vb:
            continue
        ma, mb = statistics.median(va), statistics.median(vb)
        delta = (mb - ma) / ma * 100 if ma else (0.0 if mb == ma else float("inf"))
        better = (delta > 0) == (k in HIGHER_IS_BETTER) if delta == delta and delta != 0 else None
        p = perm_p(list(va), list(vb))
        mark = "" if better is None else ("+" if better else "-")
        print(f"{case:16} {k:15} {fmt(va):>30} {fmt(vb):>30} {delta:+6.1f}%{mark} {'' if p is None else f'{p:.2f}'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--label", required=True)
    r.add_argument("--repeat", type=int, default=1)
    r.add_argument("--p", action="append", default=[], help="extra launch param key=value (env=A=1,B=2, view=WxH)")
    r.add_argument("cases", nargs="*")
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    c.add_argument("cases", nargs="*")
    s = sub.add_parser("show")
    s.add_argument("label")
    a = ap.parse_args()
    {"run": cmd_run, "compare": cmd_compare, "show": cmd_show}[a.cmd](a)


if __name__ == "__main__":
    main()
