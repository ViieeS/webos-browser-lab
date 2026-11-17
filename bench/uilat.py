#!/usr/bin/env python3
"""Browser UI latency in WebOS-Chromium builds from Chromium's own histograms, read over CDP (Browser.getHistograms).
Keys go in as the remote's own events (evkeys on /dev/input/event10, "LGE Network Input", which the compositor reads; event1 it does not), so the LG input -> compositor -> Wayland path is
exercised, but Chromium's metrics start at its event timestamp and do not include that path.
usage: uilat.py -b cr151own,cr151 <rounds> <scenario>...      scenarios: omnibox tabs keyscroll keyfocus
         a build tag may carry a variant: cr151own+nosmooth, cr151own+nogpu (extra flag in browser.flags, VARIANTS)
       uilat.py trace <tag> <scenario> <out.json>   (one run under Chromium tracing, categories TRACE_CATEGORIES)
       uilat.py probe <evkeys args...>     (app already running with DevTools: press keys, print every changed histogram)
Needs, per app: --remote-debugging-port=9225 in /tmp/<appid>/browser.flags, tcprelay <TV LAN ip> 9226 -> 9225,
/media/developer/temp/evkeys. Every launch is a fresh process, so Startup.* is read once per run.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bench  # noqa: E402
from inspector import WebSocket  # noqa: E402

TV = os.environ["TV_HOST"]
CDP = f"{TV}:9226"
EVKEYS = "/media/developer/temp/evkeys /dev/input/event10"
APPS = {"cr151own": "com.viiees.cr151", "cr151": "org.nativechromium.browser"}
PREFIXES = ("EventLatency.KeyPressed", "Omnibox.Views.PopupFirstPaint", "Omnibox.CharTypedToRepaintLatency", "Browser.Tabs.TotalSwitchDuration3",
            "TabStrip.TimeToSwitch", "Startup.BrowserWindow", "Startup.FirstWebContents.NonEmptyPaint3",
            "Startup.BrowserMessageLoopStartTime", "Startup.LoadTime")
CTRL, A, T, TAB, ESC, DOWN, F6, BACKSPACE = 29, 30, 20, 15, 1, 108, 64, 14
WIKIPEDIA = [17, 23, 37, 23, 25, 18, 32, 23, 30]
GAP_MS = 300
SCENARIOS = {   # evkeys arguments; each press is spaced GAP_MS so one paint ends before the next key
    # F6 moves focus from the page to the omnibox (Ctrl+L right after launch went to the page). Type 9 letters,
    # select all, delete; 3 times = 27 typed characters. Suggestions come from Google, as for a person typing.
    "omnibox": [str(F6), "w600"] + [*map(str, WIKIPEDIA), f"{CTRL}+{A}", str(BACKSPACE), "w800"] * 3
               + [str(ESC), str(ESC)],
    # 20 Tab presses in the page: focus moves from link to link (the focus ring repaints)
    "keyfocus": ["w300"] + [str(TAB)] * 20,
    # a second tab once, then 20 tab switches
    "tabs": [f"{CTRL}+{T}", "w2500"] + [f"{CTRL}+{TAB}", "w400"] * 20,
    # 20 Down presses in the page (keyboard scroll), the content key path
    "keyscroll": ["w300"] + [str(DOWN)] * 20,
}
VARIANTS = {"nosmooth": "--disable-smooth-scrolling",
            "nospatnav": "--blink-settings=spatialNavigationEnabled=false",
            "nogpu": "--disable-gpu"}   # the launcher's own fallback when its GPU probe fails: software raster+compositing
# EventLatency and PipelineReporter (cc,input / cc,benchmark) carry Chromium's own stage split of each latency
TRACE_CATEGORIES = os.environ.get("UILAT_CATS", "cc,benchmark,input,latencyInfo").split(",")   # UILAT_CATS: more
SHOW = ("",) if os.environ.get("UILAT_ALL") else PREFIXES   # UILAT_ALL=1: every changed histogram
PAGE = f"{bench.HTTP}/pages/wiki/en.wikipedia.org/wiki/Television.html"


class Browser:
    def __init__(self):
        ver = json.load(urllib.request.urlopen(f"http://{CDP}/json/version", timeout=20))
        self.ws = WebSocket(CDP, ver["webSocketDebuggerUrl"].split(CDP, 1)[1])
        self.n = 0

    def call(self, method, params=None, timeout=30):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg["result"]
        raise TimeoutError(method)

    def sync_children(self):
        """Child processes (renderer: EventLatency.*) keep histograms to themselves until the browser fetches them.
        Browser.getHistograms does not fetch, chrome://histograms does, so open it in a background tab and close it."""
        tid = self.call("Target.createTarget", {"url": "chrome://histograms", "background": True})["targetId"]
        time.sleep(3)
        self.call("Target.closeTarget", {"targetId": tid})

    def event(self, method, timeout=120):
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = json.loads(self.ws.recv())
            if msg.get("method") == method:
                return msg["params"]
        raise TimeoutError(method)

    def trace_to(self, path):
        """Ends tracing started with Tracing.start and saves the JSON trace."""
        self.call("Tracing.end")
        stream = self.event("Tracing.tracingComplete")["stream"]
        with open(path, "w") as f:
            while True:
                chunk = self.call("IO.read", {"handle": stream, "size": 1 << 20})
                f.write(chunk["data"])
                if chunk.get("eof"):
                    break
        self.call("IO.close", {"handle": stream})

    def histograms(self, delta):
        return {h["name"]: h for h in self.call("Browser.getHistograms", {"delta": delta})["histograms"]}


def stats(h):
    """count, mean and the median bucket's lower bound (Chromium buckets are exponential, so the median is a range)."""
    n = h["count"]
    acc, med = 0, None
    for b in sorted(h["buckets"], key=lambda b: b["low"]):
        acc += b["count"]
        if med is None and acc * 2 >= n:
            med = b["low"]
    return f"n={n} mean={h['sum'] / n:.1f} p50>={med}" if n else "n=0"


def show(hs, prefixes=PREFIXES):
    return "; ".join(f"{name} {stats(h)}" for name, h in sorted(hs.items())
                     if name.startswith(prefixes) and h["count"])


def press(keys):
    bench.tv(f"{EVKEYS} {GAP_MS} {' '.join(keys)}", timeout=120)


def fire(cmd):
    try:
        bench.tv(cmd, timeout=30)
    except subprocess.TimeoutExpired:
        pass


def close_all():
    return "".join(f"luna-send -n 1 luna://com.webos.applicationManager/closeByAppId '{{\"id\":\"{a}\"}}' >/dev/null; "
                   for a in (*APPS.values(), "com.webos.app.screensaver"))


def wait_cdp(seconds=40):
    deadline = time.time() + seconds
    while True:
        try:
            return Browser()
        except Exception:
            if time.time() > deadline:
                raise
            time.sleep(1)


def start(tag):
    """Fresh launch of the build in tag ("cr151own" or "cr151own+nosmooth") with DevTools and the variant's flag."""
    base, _, variant = tag.partition("+")
    app = APPS[base]
    flags = " ".join(["--remote-debugging-port=9225", VARIANTS[variant] if variant else ""])
    launch = json.dumps({"id": app, "params": {"target": PAGE}})
    fire(f"{close_all()}sleep 4; printf '%s\\n' {flags} > /tmp/{app}/browser.flags; "
         f"luna-send -n 1 luna://com.webos.applicationManager/launch '{launch}' >/dev/null")
    br = wait_cdp()
    time.sleep(10)   # page load and the after-startup tasks
    return br


def run(tag, scenario, rnd):
    br = start(tag)
    print(f"{tag} {scenario} #{rnd} startup: {show(br.histograms(False), ('Startup.',))}", flush=True)
    br.sync_children()
    br.histograms(True)   # reset the delta
    press(SCENARIOS[scenario])
    time.sleep(2)
    br.sync_children()
    print(f"{tag} {scenario} #{rnd}: {show(br.histograms(True), SHOW)}", flush=True)
    br.ws.sock.close()
    fire(close_all())


if sys.argv[1] == "trace":
    tag, scenario, out = sys.argv[2:5]
    br = start(tag)
    br.call("Tracing.start", {"traceConfig": {"includedCategories": TRACE_CATEGORIES, "recordMode": "recordUntilFull"},
                              "transferMode": "ReturnAsStream", "streamFormat": "json"})
    press(SCENARIOS[scenario])
    time.sleep(2)
    br.trace_to(out)
    fire(close_all())
    sys.exit()
if sys.argv[1] == "probe":
    br = Browser()
    br.histograms(True)
    press(sys.argv[2:])
    time.sleep(2)
    print(show(br.histograms(True), ("",)))
    sys.exit()
args = sys.argv[1:]
tags = ["cr151own", "cr151"]
if args[0] == "-b":
    tags, args = args[1].split(","), args[2:]
stamp = int(time.time()) % 100000
for r in range(int(args[0])):
    for scenario in args[1:]:
        for tag in tags:
            run(tag, scenario, f"{stamp}-{r}")
