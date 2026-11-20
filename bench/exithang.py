#!/usr/bin/env python3
"""Why menu > Exit leaves the browser process alive when a New Tab page is open.
Opens an NTP (Ctrl+T), closes example.com as a non-last tab, disconnects DevTools, picks menu > Exit, then watches
the process for up to 120 s and dumps the state of its threads (comm, state, wchan) at 15 s.
usage: exithang.py [ntp|plain|maps]   plain = control without the NTP; maps = Google Maps open, closed by webOS
(applicationManager/closeByAppId) instead of the menu. Needs TV_HOST, tcprelay 9226 -> 9225, evkeys.
"""
import sys
import time

import bench
import lasttab as L
import uilat

THREADS = ("P=$(pgrep -o -f 'com.viiees.chromiumtv/browser/chrome '); echo pid $P; "
           "for t in /proc/$P/task/*; do echo $(cat $t/comm) $(cut -d' ' -f3 $t/stat) $(cat $t/wchan); done "
           "| sort | uniq -c | sort -rn | head -40; echo main: $(cat /proc/$P/wchan) $(cat /proc/$P/syscall)")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "ntp"
    br = uilat.start("chromiumtv", "https://www.google.com/maps" if mode == "maps" else L.PAGE)
    if mode == "maps":
        time.sleep(10)   # map tiles and animations running
    if mode == "ntp":
        uilat.press(["29+20", "w2500", "29+2", "w1000", "29+17"])   # Ctrl+T, Ctrl+1, Ctrl+W
        time.sleep(3)
    print(mode, "pages:", L.pages(), flush=True)
    br.ws.sock.close()
    time.sleep(2)
    if mode == "maps":
        bench.tv("luna-send -n 1 luna://com.webos.applicationManager/closeByAppId '{\"id\":\"%s\"}'" % L.APP)
    else:
        uilat.press(["56+18", "w1000", "103", "w600", "28"])   # Alt+E, Up (wraps to Exit), Enter
    t0 = time.time()
    dumped = False
    while time.time() - t0 < 120:
        if not L.alive():
            print(f"{mode}: process gone after {time.time() - t0:.0f} s", flush=True)
            return
        if not dumped and time.time() - t0 > 15:
            print(bench.tv(THREADS), flush=True)
            dumped = True
        time.sleep(3)
    print(f"{mode}: still alive after 120 s", flush=True)


if __name__ == "__main__":
    main()
