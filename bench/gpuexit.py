#!/usr/bin/env python3
"""Does Chromium TV crash on exit with the GPU on? The launcher wrote gpu.state "bad (status 11 after 27 s)": a
SIGSEGV soon after a GPU-on start, with no SIGTERM from webOS, so most likely on Chrome's own exit path (Back twice
on a tab's first page, patch 0057, or menu > Exit). Each round launches the app on a page with the GPU forced on,
waits, exits one way, and reads the launcher's "chrome exited, status N" from media.log.
Status 0 = clean; 11 / 139 = SIGSEGV (139 with a core); 15 / 9 = stopped by the launcher after the quit timeout.
usage: gpuexit.py <rounds> [back,menu,close] [url]     GPUEXIT_CORE=1: allow a core for these launches (run.sh
says "ulimit -c 0"; the edit goes through inputlat's run.sh.ab copy and is put back at the end). The core lands in
the app folder on flash, about 100 MB each.
Needs TV_HOST, tcprelay <TV LAN ip> 9226 -> 9225, evkeys; "gpu=on" in /tmp/com.viiees.chromiumtv/media.opts.
"""
import sys
import time

import os

import bench
import inputlat
import uilat

APP = uilat.APPS["chromiumtv"]
LOG = f"/tmp/{APP}/media.log"
BACK = "412"   # the remote's Back on event10 (patch 0057 reads evdev 412)
WAYS = {
    "back": lambda: uilat.press([BACK, "w700", BACK]),   # first page: Back shows the toast, a second Back exits
    "menu": lambda: uilat.press(["56+18", "w1000", "103", "w600", "28"]),   # Alt+E, Up wraps to Exit, Enter
    "close": lambda: uilat.fire(f"luna-send -n 1 luna://com.webos.applicationManager/closeByAppId "
                                f"'{{\"id\":\"{APP}\"}}' >/dev/null"),
}


def one(way, url, dwell):
    br = uilat.start("chromiumtv", url)
    gpu = br.call("SystemInfo.getInfo")["gpu"]["featureStatus"]["gpu_compositing"]
    br.ws.sock.close()
    time.sleep(dwell)
    WAYS[way]()
    for _ in range(20):
        time.sleep(1)
        out = bench.tv(f"grep -h 'chrome exited\\|gpu:' {LOG} | tail -n 3")
        if "chrome exited" in out:
            break
    status = [ln for ln in out.splitlines() if "chrome exited" in ln]
    print(f"GPUEXIT way={way} gpu_compositing={gpu} dwell={dwell} -> "
          f"{status[-1].split('status')[-1].strip() if status else 'still running'} | "
          f"{' / '.join(ln.split(' ', 1)[-1] for ln in out.splitlines() if 'gpu:' in ln)}", flush=True)
    if not status:
        uilat.fire(uilat.close_all())


def main():
    rounds = int(sys.argv[1])
    ways = sys.argv[2].split(",") if len(sys.argv) > 2 else list(WAYS)
    url = sys.argv[3] if len(sys.argv) > 3 else "https://en.wikipedia.org/wiki/Television"
    assert "gpu=" in bench.tv(f"cat /tmp/{APP}/media.opts 2>/dev/null"), "put gpu=on into media.opts first"
    core = os.environ.get("GPUEXIT_CORE") == "1"
    if core:
        R = inputlat.RUNSH
        out = bench.tv(f"[ -f {R}.ab ] || cp -p {R} {R}.ab; sed -i 's|^ulimit -c 0$|ulimit -c unlimited|' {R}; "
                       f"grep -c '^ulimit -c unlimited$' {R}")
        assert out.strip().splitlines()[-1] == "1", f"run.sh not edited: {out}"
    try:
        for r in range(rounds):
            for way in ways:
                one(way, url, 12 + 5 * (r % 3))
    finally:
        if core:
            print("run.sh", inputlat.runsh_restore(), flush=True)


if __name__ == "__main__":
    main()
