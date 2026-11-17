#!/usr/bin/env python3
"""Measure the browser on the TV with one fixed suite, so builds compare line by line.

Every case starts a fresh browser process. The host prints "LOAD <ms> <uri>" per finished
navigation; bench.html prints "BENCH ..." and the autoscroll probe prints "SCROLL fps=.. slow=..".
usage: perf.py <tv-ip> [case-name ...]
"""
import json
import os
import subprocess
import time
import sys

TVTELNET = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bench", "tvtelnet.py")
APP = "com.viiees.browser"
LOG = f"/var/palm/jail/{APP}/tmp/browser.log"
BENCH = f"file:///media/developer/apps/usr/palm/applications/{APP}/bench.html"
WIKI = "https://en.wikipedia.org/wiki/Television"

# name -> (launch params, seconds to wait)
CASES = {
    "bench": ({"url": BENCH}, 25),
    "cold-google": ({"url": "https://www.google.com"}, 30),
    "cold-wiki": ({"url": WIKI}, 30),
    "cold-youtube": ({"url": "https://www.youtube.com"}, 40),
    "nav-google-wiki": ({"url": "https://www.google.com", "then": WIKI}, 40),   # 2nd LOAD = warm nav
    "scroll-wiki": ({"url": WIKI, "autoscroll": "1"}, 40),
    "scroll-reddit": ({"url": "https://www.reddit.com", "autoscroll": "1"}, 50),
    "wheel-wiki": ({"url": WIKI, "autoscroll": "wheel"}, 25),          # user path: scrolling thread
    "wheel-youtube": ({"url": "https://www.youtube.com", "autoscroll": "wheel"}, 35),
    # browserbench.org suites; "probe" is the CSS selector of the final score, the wait a ceiling.
    "speedometer": ({"url": "https://browserbench.org/Speedometer3.1/?startAutomatically&iterationCount=3",
                     "probe": "#result-number"}, 1800),
    "speedometer-local": ({"url": "http://127.0.0.1:8099/speedometer3.1/index.html?startAutomatically&iterationCount=2",
                           "probe": "#result-number"}, 2400),
    # Speedometer crashes the web process within a minute on the softfp JIT build: the reproducer.
    "crash-speedometer": ({"url": "https://browserbench.org/Speedometer3.1/?startAutomatically&iterationCount=2",
                           "probe": "#result-number"}, 1800),
}
REPORT = f"grep -E '^LOAD|BENCH|SCROLL|^PRESENT|^CRASH|PROBE' {LOG}; ps -eo rss,comm | grep -c WPEWebProcess"


def tv(ip, cmd):
    return subprocess.run(["python3", TVTELNET, ip, cmd], capture_output=True, text=True, timeout=240).stdout


def run(ip, name, extra):
    params, wait = CASES[name]
    params = {**params, **extra}
    launch = json.dumps({"id": APP, "params": params})
    start = (f"luna-send -n 1 luna://com.webos.applicationManager/closeByAppId '{{\"id\":\"{APP}\"}}' >/dev/null; "
             f"sleep 3; luna-send -n 1 luna://com.webos.applicationManager/launch '{launch}' >/dev/null")
    if "probe" not in params:
        out = tv(ip, f"{start}; sleep {wait}; {REPORT}")
    else:
        # tvtelnet gives up after 180 s, so long suites are polled from here until the score appears.
        tv(ip, start)
        deadline = time.time() + wait
        while True:
            time.sleep(30)
            out = tv(ip, REPORT)
            if "PROBE" in out or "CRASH" in out or time.time() > deadline:
                break
    lines = [l.split("CONSOLE LOG ")[-1] for l in out.splitlines() if l.strip()]
    procs = lines.pop() if lines and lines[-1].isdigit() else "?"
    results = [l.split(" http")[0] if l.startswith("LOAD") else l for l in lines if not l.startswith("PRESENT")]
    # Frames that reached the screen during the probe: the PRESENT seconds just before SCROLL.
    scroll_at = next((i for i, l in enumerate(lines) if l.startswith("SCROLL")), None)
    if scroll_at is not None:
        shown = [int(l.split("frames=")[1].split()[0]) for l in lines[max(0, scroll_at - 8):scroll_at]
                 if l.startswith("PRESENT")]
        if shown:
            results.append(f"screen_fps={sum(shown) / len(shown):.1f}")
    return f"{name}: " + " | ".join(results or ["no result"]) + f" | webprocs={procs}"


def main():
    # perf.py <ip> [--p key=value ...] [case ...]; e.g. --p view=1280x720 --p env=WEBKIT_X=1,JSC_Y=0
    args = sys.argv[1:]
    ip, extra = args.pop(0), {}
    while args[:1] == ["--p"]:
        key, value = args[1].split("=", 1)
        extra[key] = value
        args = args[2:]
    for name in args or list(CASES):
        print(run(ip, name, extra), flush=True)


if __name__ == "__main__":
    main()
