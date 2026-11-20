#!/usr/bin/env python3
"""Patch 0107 check: closing the last tab opens a New Tab page instead of quitting; menu > Exit still quits.
Each case starts from a single tab, closes it one way, then reads the tabs over DevTools.
usage: lasttab.py            Needs TV_HOST, tcprelay <TV LAN ip> 9226 -> 9225, /media/developer/temp/evkeys.
"""
import time

import adblock_run as ab
import bench
import uilat

APP = uilat.APPS["chromiumtv"]
CTRL, W, ALT, E, UP, ENTER = 29, 17, 56, 18, 103, 28
PAGE = "https://example.com/"


def pages():
    return [t["url"] for t in ab.targets() if t["type"] == "page"]


def one_tab(br, url=PAGE):
    """Opens url in a new tab and closes every other page, leaving exactly one tab."""
    tid = br.call("Target.createTarget", {"url": url})["targetId"]
    time.sleep(3)
    for t in ab.targets():
        if t["type"] == "page" and t["id"] != tid:
            br.call("Target.closeTarget", {"targetId": t["id"]})
    time.sleep(2)
    return tid


def alive():
    # the trailing space skips chrome_crashpad_handler
    return "up" in bench.tv(f"pgrep -f '{APP}/browser/chrome ' >/dev/null && echo up || echo down")


def case(name, br, close):
    tid = one_tab(br)
    before = pages()
    close(tid)
    time.sleep(4)
    print(f"{name}: before {before} -> after {pages() if alive() else 'browser gone'}", flush=True)


def main():
    br = uilat.start("chromiumtv", PAGE)
    case("Ctrl+W", br, lambda tid: uilat.press([f"{CTRL}+{W}"]))
    case("window.close()", br, lambda tid: ab.evaluate(tid, "window.close()", user_gesture=True))
    case("DevTools Target.closeTarget", br, lambda tid: br.call("Target.closeTarget", {"targetId": tid}))
    # menu > Exit: Alt+E opens the app menu, Up wraps to its last item, Exit
    uilat.press([f"{ALT}+{E}", "w1000", str(UP), "w600", str(ENTER)])
    for waited in (3, 10, 30):
        time.sleep(waited - (3 if waited == 10 else 10 if waited == 30 else 0))
        print(f"menu > Exit, {waited} s:", "browser still running" if alive() else "browser gone", flush=True)


if __name__ == "__main__":
    main()
