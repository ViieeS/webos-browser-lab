#!/usr/bin/env python3
"""Which user agent keeps youtube.com/tv on its TV interface (leanback) in Chromium TV? With TV Tools' "Web0S ...
Chrome/151" user agent it redirects to the desktop site. Runs without extensions (TV Tools would rewrite the
header), sets each candidate with CDP Emulation.setUserAgentOverride (header and navigator), opens /tv and reports
where it ended up and whether leanback's ytlr-* elements are there. A screenshot per candidate goes to build/ytua/.
usage: ytua.py [candidate name...]     YTUA_TAG: the launch tag (default chromiumtv+zeroext; "chromiumtv" keeps the
shipped extensions, with candidate "desktop" = no override, TV Tools decides)
Needs TV_HOST, tcprelay <TV LAN ip> 9226 -> 9225.
"""
import base64
import json
import os
import sys
import time
import urllib.request

import uilat
from inspector import WebSocket

TAG = os.environ.get("YTUA_TAG", "chromiumtv+zeroext")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "ytua")
CANDIDATES = {
    "tvtools": "Mozilla/5.0 (Web0S; Linux/SmartTV) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 "
               "Safari/537.36 WebAppManager",
    "webos-wam79": "Mozilla/5.0 (Web0S; Linux/SmartTV) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.79 "
                   "Safari/537.36 WebAppManager",
    "tizen": "Mozilla/5.0 (SMART-TV; LINUX; Tizen 6.0) AppleWebKit/537.36 (KHTML, like Gecko) 76.0.3809.146/6.0 TV "
             "Safari/537.36",
    "cobalt": "Mozilla/5.0 (X11; Linux armv7l) Cobalt/25.lts.30.1034943-gold (unlike Gecko) v8/8.8.278.17-jit gles "
              "Starboard/15, LGE_webOS_2021/06.50.03 (LGE, OLED55C1, wired)",
    "ps4": "Mozilla/5.0 (PS4; Leanback Shell) Gecko/20100101 Firefox/65.0 LeanbackShell/01.00.01.75 Sony PS4/ "
           "(PS4, , no, CH)",
    "desktop": "",   # Chromium's own user agent, for reference
}
PROBE = """JSON.stringify({url: location.href, title: document.title,
  ytlr: document.querySelectorAll('[class*=ytlr], ytlr-app, ytlr-surface-page, ytlr-tile-renderer').length,
  desktop: !!document.querySelector('ytd-app'), text: (document.body && document.body.innerText || '').slice(0, 120)})"""


class Page:
    def __init__(self):
        page = next(t for t in json.load(urllib.request.urlopen(f"http://{uilat.CDP}/json/list", timeout=20))
                    if t["type"] == "page")
        self.ws, self.n = WebSocket(uilat.CDP, "/devtools/page/" + page["id"]), 0

    def call(self, method, params=None, timeout=60):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.n:
                return m.get("result", {})
        raise TimeoutError(method)


def main():
    names = sys.argv[1:] or list(CANDIDATES)
    os.makedirs(OUT, exist_ok=True)
    for name in names:
        uilat.start(TAG, "about:blank").ws.sock.close()
        page = Page()
        if CANDIDATES[name]:
            page.call("Emulation.setUserAgentOverride", {"userAgent": CANDIDATES[name]})
        page.call("Page.navigate", {"url": "https://www.youtube.com/tv"})
        time.sleep(20)
        probe = json.loads(page.call("Runtime.evaluate", {"expression": PROBE, "returnByValue": True})["result"]["value"])
        shot = page.call("Page.captureScreenshot", {"format": "jpeg", "quality": 50})
        with open(os.path.join(OUT, f"{TAG}-{name}.jpg"), "wb") as f:
            f.write(base64.b64decode(shot["data"]))
        print("YTUA", json.dumps({"tag": TAG, "ua": name, **probe}, ensure_ascii=False), flush=True)
        page.ws.sock.close()
    uilat.fire(uilat.close_all())


if __name__ == "__main__":
    main()
