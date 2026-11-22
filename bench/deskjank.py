#!/usr/bin/env python3
"""Control for the TV's "~90 % late frames": the same wheel pattern as inputlat.py's WHEEL, sent to desktop Chrome.
If desktop Chrome also reports ~90 % in Event.ScrollJank.DelayedFramesPercentage4, the number comes from the
input pattern (single notches 80 ms apart), not from the TV.
Wheel events go in through CDP Input.dispatchMouseEvent on the page target (the TV runs used evdev).
usage: deskjank.py <chrome binary> <profile dir> [rounds, default 2] [gap ms, default 80]
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inspector import WebSocket  # noqa: E402

PORT = 9333
CDP = f"127.0.0.1:{PORT}"
URL = "https://en.wikipedia.org/wiki/Television"
# inputlat.WHEEL: 12 notches down, pause, 12 down, pause, 6 up. One notch is deltaY 120.
PATTERN = [120] * 12 + [None] + [120] * 12 + [None] + [-120] * 6
NAMES = ("Event.ScrollJank.DelayedFramesPercentage4.PerScroll", "Event.ScrollJank.DelayedFramesPercentage.PerScroll",
         "Event.ScrollJank.MissedVsyncs.PerFrame", "EventLatency.MouseWheel.TotalLatency")


class Cdp:
    def __init__(self, path):
        self.ws, self.n = WebSocket(CDP, path), 0

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


def stats(h):
    n = h["count"]
    return f"n={n} mean={h['sum'] / n:.1f}" if n else "n=0"


def page_target():
    for t in json.load(urllib.request.urlopen(f"http://{CDP}/json/list", timeout=10)):
        if t["type"] == "page" and t["url"].startswith(URL):
            return t["webSocketDebuggerUrl"].split(CDP, 1)[1]
    raise RuntimeError("no Wikipedia page target")


def one_round(browser, gap_ms):
    page = Cdp(page_target())
    page.call("Page.reload")
    time.sleep(6)
    browser.call("Browser.getHistograms", {"delta": True})   # zero the delta
    x, y = 640, 360
    page.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    time.sleep(1)
    for d in PATTERN:
        if d is None:
            time.sleep(1.5)
            continue
        page.call("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": x, "y": y, "deltaX": 0, "deltaY": d})
        time.sleep(gap_ms / 1000)
    time.sleep(3)
    # renderer and GPU processes keep their histograms until chrome://histograms fetches them
    tid = browser.call("Target.createTarget", {"url": "chrome://histograms", "background": True})["targetId"]
    time.sleep(3)
    browser.call("Target.closeTarget", {"targetId": tid})
    hs = {h["name"]: h for h in browser.call("Browser.getHistograms", {"delta": True})["histograms"]}
    return {n: stats(hs[n]) if n in hs else "absent" for n in NAMES}


def main():
    chrome, profile = sys.argv[1], sys.argv[2]
    rounds = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    gap = int(sys.argv[4]) if len(sys.argv) > 4 else 80
    proc = subprocess.Popen([chrome, f"--remote-debugging-port={PORT}", "--remote-debugging-address=127.0.0.1",
                             f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
                             "--window-size=1280,720", URL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                ver = json.load(urllib.request.urlopen(f"http://{CDP}/json/version", timeout=2))
                break
            except OSError:
                time.sleep(0.5)
        else:
            raise RuntimeError("Chrome did not open its CDP port")
        print("browser", ver["Browser"], "gap_ms", gap, flush=True)
        time.sleep(5)
        browser = Cdp(ver["webSocketDebuggerUrl"].split(CDP, 1)[1])
        for r in range(rounds):
            print("DESKJANK", json.dumps({"round": r, "gap_ms": gap, "hist": one_round(browser, gap)}), flush=True)
    finally:
        proc.terminate()
        proc.wait(timeout=20)


if __name__ == "__main__":
    main()
