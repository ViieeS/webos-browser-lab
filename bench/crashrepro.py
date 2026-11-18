#!/usr/bin/env python3
"""Does a page crash the renderer? Fresh launch, the URL in the start tab, then every 5 s for WAIT_S seconds:
the tab answers, crashed (Inspector.targetCrashed), or busy. Lists crashpad dumps written during the run.
usage: crashrepro.py <tag>[,<tag>...] <url> [wait seconds, default 60]   tags: uilat.APPS (cr151 = 0.0.66) and cr151b
Needs TV_HOST, tcprelay <TV LAN ip> 9226 -> 9225, lighttpd (bench/lighttpd.conf).
"""
import json
import sys
import time

import adblock_run as ab
import bench
import uilat

uilat.APPS["cr151b"] = "com.viiees.cr151b"
DUMPS = "ls -1 --full-time '/media/developer/apps/usr/palm/applications/{app}/data/chromium/Crash Reports/pending/' " \
        "2>/dev/null | grep dmp | awk '{{print $7, $9}}' | sort | tail -n 5"


def watch(target_id, seconds):
    ws = ab.WebSocket(uilat.CDP, "/devtools/page/" + target_id)
    ws.send(json.dumps({"id": 1, "method": "Inspector.enable"}))
    ws.sock.settimeout(1)
    start, state = time.time(), "ok"
    while time.time() - start < seconds:
        try:
            m = json.loads(ws.recv())
        except OSError:
            continue
        if m.get("method") == "Inspector.targetCrashed":
            state = f"crashed at +{time.time() - start:.0f}s"
            break
    ws.sock.close()
    return state


def main():
    tags, url = sys.argv[1].split(","), sys.argv[2]
    wait = int(sys.argv[3]) if len(sys.argv) > 3 else 60
    bench.tv("wget -q -O /dev/null http://127.0.0.1:8099/pages/spatnav.html || "
             "lighttpd -f /media/developer/bench/lighttpd.conf")
    for tag in tags:
        app = uilat.APPS[tag.partition("+")[0]]
        before = bench.tv(DUMPS.format(app=app))
        br = uilat.start(tag, page=ab.START_PAGE)
        target = ab.page_target()["id"]
        ab.open_url(url)
        print(f"{tag} {url}: {watch(target, wait)}", flush=True)
        after = bench.tv(DUMPS.format(app=app))
        new = [l for l in after.splitlines() if l not in before.splitlines()]
        print(f"{tag} new dumps: {new}", flush=True)
        br.ws.sock.close()
        uilat.fire(uilat.close_all())


if __name__ == "__main__":
    main()
