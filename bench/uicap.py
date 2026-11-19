#!/usr/bin/env python3
"""Screenshots of the browser's own UI (tab strip, address bar with its suggestions, the app menu) for a font check.
Keys go in through evkeys (event10, the compositor's network input), screens come from webOS's capture service.
usage: uicap.py <tag> <out prefix>      (writes <prefix>_page.png, _omnibox.png, _menu.png)
Needs TV_HOST, tcprelay <TV LAN ip> 9226 -> 9225, /media/developer/temp/evkeys.
"""
import base64
import sys
import time

import bench
import uilat

ALT, E, ESC, CTRL, L = 56, 18, 1, 29, 38
PAGE = "https://ru.wikipedia.org/wiki/%D0%A2%D0%B5%D0%BB%D0%B5%D0%B2%D0%B8%D0%B4%D0%B5%D0%BD%D0%B8%D0%B5"
WORD = [17, 23, 37, 23, 25, 18, 32, 23, 30]   # "wikipedia"


def capture(path):
    shot = "/tmp/uicap.png"
    bench.tv(f"luna-send -n 1 luna://com.webos.service.capture/executeOneShot "
             f"'{{\"path\":\"{shot}\",\"method\":\"DISPLAY\",\"format\":\"PNG\",\"width\":1920,\"height\":1080}}' >/dev/null")
    data = bench.tv(f"base64 {shot}; rm -f {shot}")
    with open(path, "wb") as f:
        f.write(base64.b64decode("".join(data.split())))


def main():
    tag, prefix = sys.argv[1], sys.argv[2]
    br = uilat.start(tag, page=PAGE)
    time.sleep(12)
    capture(f"{prefix}_page.png")
    uilat.press([str(ESC), "w800", f"{CTRL}+{L}", "w800", *map(str, WORD), "w2500"])   # Esc: the translate bubble
    capture(f"{prefix}_omnibox.png")
    uilat.press([str(ESC), str(ESC), "w600", f"{ALT}+{E}", "w1500"])
    capture(f"{prefix}_menu.png")
    uilat.press([str(ESC), "w300"])
    br.ws.sock.close()
    uilat.fire(uilat.close_all())


if __name__ == "__main__":
    main()
