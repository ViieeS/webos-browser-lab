#!/usr/bin/env python3
"""Checks the cookie-banner add-on as the installed Chromium TV ships it: run.sh's own --load-extension list, a
throwaway profile. Prints the loaded extensions' service workers, then the consent probe on a few sites.
usage: consent_shipped.py [site name...]     default: ikea cookiebot bbc youtube (names from consent_run.SITES)
CSHIPPED_EXTRA: more browser flags, e.g. another --load-extension list to test a changed add-on.
Needs TV_HOST, tcprelay <TV LAN ip> 9226 -> 9225.
"""
import json
import os
import sys
import time

import adblock_run as ab
import consent_run as cr
import uilat

uilat.VARIANTS["cshipped"] = f"--user-data-dir={cr.PROFILE} {os.environ.get('CSHIPPED_EXTRA', '')}".strip()


def main():
    names = sys.argv[1:] or ["ikea", "cookiebot", "bbc", "youtube"]
    cr.bench.tv(f"rm -rf {cr.WORK} && mkdir -p {cr.WORK} && chown $(stat -c %u:%g /tmp/{cr.APP}) {cr.WORK}")
    uilat.start("chromiumtv+cshipped", cr.START_PAGE)
    time.sleep(5)
    workers = sorted({t["url"].split("/")[2] + " " + t["url"].split("/")[-1] for t in ab.targets()
                      if t["type"] == "service_worker"})
    print("service workers:", workers, flush=True)
    page = cr.Page()
    page.call("Network.enable")
    urls = dict(cr.SITES)
    for name in names:
        page.goto(urls[name])
        time.sleep(cr.SETTLE_S)
        probe = json.loads(page.eval(cr.PROBE))
        print(json.dumps({"site": name, "visible": probe["visible"], "record": probe["record"],
                          "cookies": cr.cookies_of_interest(page)}, ensure_ascii=False)[:600], flush=True)
    uilat.fire(uilat.close_all())


if __name__ == "__main__":
    main()
