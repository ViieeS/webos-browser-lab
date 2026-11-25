#!/usr/bin/env python3
"""Which sites give Chromium TV a TV interface, and does TV Tools' user agent get it? Opens each site twice in the
installed Chromium TV with no extensions and a throwaway profile: once with TV Tools' TV user agent (set with CDP
Emulation.setUserAgentOverride, header and navigator), once with Chromium's own. Reports where each one ended up,
the title, layout width, a few interface markers and the first page text. Screenshots go to build/tvsites/.
usage: tvsites.py [tv|desktop] [site name...]     default: both passes, all SITES
Needs TV_HOST, tcprelay <TV LAN ip> 9226 -> 9225.
"""
import base64
import json
import os
import sys
import time

import uilat
import ytua

APP = uilat.APPS["chromiumtv"]
PROFILE = f"/tmp/{APP}/tvsites"
uilat.VARIANTS["tvsites"] = f"--disable-extensions --user-data-dir={PROFILE}"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "tvsites")
SETTLE_S = 15
UAS = {"tv": ytua.CANDIDATES["tvtools"], "desktop": ""}
SITES = [   # (name, url): video and music services with TV apps, and a few everyday sites for contrast
    ("youtube", "https://www.youtube.com/"),
    ("youtube-tv", "https://www.youtube.com/tv"),
    ("youtube-music", "https://music.youtube.com/"),
    ("twitch", "https://www.twitch.tv/"),
    ("vimeo", "https://vimeo.com/"),
    ("dailymotion", "https://www.dailymotion.com/"),
    ("netflix", "https://www.netflix.com/"),
    ("primevideo", "https://www.primevideo.com/"),
    ("disneyplus", "https://www.disneyplus.com/"),
    ("iplayer", "https://www.bbc.co.uk/iplayer"),
    ("itvx", "https://www.itv.com/"),
    ("channel4", "https://www.channel4.com/"),
    ("plutotv", "https://pluto.tv/"),
    ("tubi", "https://tubitv.com/"),
    ("plex", "https://app.plex.tv/"),
    ("spotify", "https://open.spotify.com/"),
    ("soundcloud", "https://soundcloud.com/"),
    ("reddit", "https://www.reddit.com/"),
    ("wikipedia", "https://en.wikipedia.org/wiki/Television"),
    ("guardian", "https://www.theguardian.com/uk"),
]
PROBE = r"""JSON.stringify({url: location.href, title: document.title, width: innerWidth,
  scrollWidth: document.documentElement.scrollWidth,
  viewport: (document.querySelector('meta[name=viewport]') || {}).content || null,
  tvMarkers: [...new Set((document.documentElement.outerHTML.match(/\b(leanback|ytlr-[a-z-]+|smart-?tv|tv-app|is-tv|10-?foot|spatial-?nav|tizen|webos)\b/gi) || []).map((s) => s.toLowerCase()))].slice(0, 8),
  unsupported: /(not supported|unsupported|update your browser|browser (is|isn.t) (not )?supported|switch to a supported)/i.test(document.body ? document.body.innerText : ''),
  text: (document.body && document.body.innerText || '').replace(/\s+/g, ' ').slice(0, 160)})"""


def run_pass(name, sites):
    uilat.bench.tv(f"rm -rf {PROFILE}")
    uilat.start("chromiumtv+tvsites", "about:blank").ws.sock.close()
    page = ytua.Page()
    if UAS[name]:
        page.call("Emulation.setUserAgentOverride", {"userAgent": UAS[name]})
    for site, url in sites:
        page.call("Page.navigate", {"url": url})
        time.sleep(SETTLE_S)
        try:
            probe = json.loads(page.call("Runtime.evaluate", {"expression": PROBE, "returnByValue": True})
                               ["result"]["value"])
            shot = page.call("Page.captureScreenshot", {"format": "jpeg", "quality": 50})
            with open(os.path.join(OUT, f"{name}-{site}.jpg"), "wb") as f:
                f.write(base64.b64decode(shot["data"]))
        except (KeyError, TimeoutError) as e:
            probe = {"error": repr(e)}
        print("TVSITE", json.dumps({"pass": name, "site": site, **probe}, ensure_ascii=False), flush=True)
    page.ws.sock.close()
    uilat.fire(uilat.close_all())
    uilat.bench.tv(f"rm -rf {PROFILE}")


def main():
    args = sys.argv[1:]
    passes = [a for a in args if a in UAS] or list(UAS)
    names = [a for a in args if a not in UAS]
    sites = [s for s in SITES if not names or s[0] in names]
    os.makedirs(OUT, exist_ok=True)
    for name in passes:
        run_pass(name, sites)


if __name__ == "__main__":
    main()
