#!/usr/bin/env python3
"""Which font draws each sample of pages/fonts.html, and screenshots of the page as the browser renders it.
For every sample: the requested family and style, and CSS.getPlatformFontsForNode (the platform font Blink used,
whether it is a downloaded web font, and how many glyphs). Screenshots via Page.captureScreenshot, one per screen.
usage: fontcheck.py <tag> <out prefix>     (tag: uilat.APPS, e.g. chromiumtv; writes <prefix>.txt and <prefix>_N.png)
Needs TV_HOST, tcprelay <TV LAN ip> 9226 -> 9225, lighttpd (bench/lighttpd.conf).
"""
import base64
import json
import sys
import time

import adblock_run as ab
import bench
import uilat


class Page:
    def __init__(self, target_id):
        self.ws = ab.WebSocket(uilat.CDP, "/devtools/page/" + target_id)
        self.n = 0

    def call(self, method, params=None):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params or {}}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m["result"]


def main():
    tag, prefix = sys.argv[1], sys.argv[2]
    br = uilat.start(tag, page=f"{bench.HTTP}/pages/fonts.html")
    time.sleep(10)   # web fonts load with display=block
    page = Page(ab.page_target()["id"])
    for d in ("DOM.enable", "CSS.enable"):
        page.call(d)
    loaded = page.call("Runtime.evaluate", {"expression": "document.fonts.ready.then(() => [...document.fonts]"
                                            ".map(f => f.family + ' ' + f.weight + ' ' + f.style + ' ' + f.status)"
                                            ".join('; '))", "awaitPromise": True, "returnByValue": True})
    out = [f"# {tag}, pages/fonts.html", f"document.fonts: {loaded['result'].get('value')}"]
    root = page.call("DOM.getDocument", {"depth": -1})["root"]["nodeId"]
    ids = page.call("DOM.querySelectorAll", {"nodeId": root, "selector": "span[id^=f]"})["nodeIds"]
    for node in ids:
        attrs = page.call("DOM.getAttributes", {"nodeId": node})["attributes"]
        label = dict(zip(attrs[::2], attrs[1::2])).get("data-label", "?")
        fonts = page.call("CSS.getPlatformFontsForNode", {"nodeId": node})["fonts"]
        used = ", ".join(f"{f['familyName']}{' [web]' if f['isCustomFont'] else ''} ({f['glyphCount']})" for f in fonts)
        out.append(f"{label:32} -> {used}")
    height = page.call("Runtime.evaluate", {"expression": "document.documentElement.scrollHeight",
                                            "returnByValue": True})["result"]["value"]
    view = page.call("Runtime.evaluate", {"expression": "innerHeight", "returnByValue": True})["result"]["value"]
    for i, y in enumerate(range(0, height, view)):
        page.call("Runtime.evaluate", {"expression": f"scrollTo(0, {y})"})
        time.sleep(1)
        png = base64.b64decode(page.call("Page.captureScreenshot", {"format": "png"})["data"])
        with open(f"{prefix}_{i}.png", "wb") as f:
            f.write(png)
    with open(f"{prefix}.txt", "w") as f:
        f.write("\n".join(out) + "\n")
    print("\n".join(out))
    page.ws.sock.close()
    br.ws.sock.close()


if __name__ == "__main__":
    main()
