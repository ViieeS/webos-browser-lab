"""Checks the launcher's gpu.state rules on the TV: only crash signals count, two in a row turn the GPU off, a run
without an early crash clears the count, a mode chosen in TV Tools "GPU" does not count and On clears the record.
usage: gpustate_test.py --yes
--yes is required: the test deletes and rewrites the installed app's data/gpu.state (a TV that fell back to software
for a reason would try the GPU again), crashes Chrome three times with SIGSEGV and changes TV Tools "GPU".
Needs TV_HOST, tcprelay <TV LAN ip> 9226 -> 9225, no gpu=on/off in media.opts. At the end, also after a failure:
gpu.state deleted, browser.flags empty. TV Tools "GPU" is back on Auto when the run passes. Exits 1 at the first check
that fails. Step 6 is the one that tests gpu.forced: step 5 starts from "bad", where the launcher counts nothing."""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uilat
from inspector import WebSocket

tv = uilat.bench.tv
APP = "com.viiees.chromiumtv"
A = f"/media/developer/apps/usr/palm/applications/{APP}"
ST = A + "/data/gpu.state"
EE = A + "/data/early-exit.log"
T = f"/tmp/{APP}"
LOG = T + "/media.log"
TVT = "ikkplgnegbekkbamfelhaeahnaddgnma"
PID = f"sed -n 's/.*chrome wrapper pid \\([0-9]*\\).*/\\1/p' {LOG} | tail -1"


def state():
    return tv(f"cat {ST} 2>/dev/null | tail -1 || true").strip() or "(none)"


def check(what, ok):
    print(f"  {'ok  ' if ok else 'FAIL'} {what}", flush=True)
    if not ok:
        raise SystemExit(1)


def start():
    """Starts the browser; returns True when Chrome runs without --disable-gpu."""
    b = uilat.start("chromiumtv")
    b.ws.sock.close()
    time.sleep(3)
    off = tv(f"tr '\\0' ' ' < /proc/$({PID})/cmdline | grep -c -- '--disable-gpu' || true").strip() != "0"
    print("  start:", tv(f"grep -E '^[0-9. ]*gpu: o|^run.sh gpu' {LOG} | tail -2").strip().replace("\n", " | "),
          flush=True)
    return not off


def close():
    uilat.fire(uilat.close_all())
    time.sleep(5)


def segv():
    tv(f"rm -f {EE}; kill -SEGV $({PID})")
    time.sleep(8)


def tvtools_gpu(mode):
    targets = json.load(urllib.request.urlopen(f"http://{uilat.CDP}/json/list", timeout=20))
    sw = [t for t in targets if t["url"].startswith(f"chrome-extension://{TVT}/") and "worker" in t["type"]]
    ws = WebSocket(uilat.CDP, "/devtools/page/" + sw[0]["id"])
    expr = (f'tvLoad().then(r => {{ r.settings.gpu = "{mode}"; return tvSave(r.settings); }})'
            '.then(() => chrome.storage.local.get("settings")).then(r => r.settings.gpu)')
    ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                        "params": {"expression": expr, "awaitPromise": True, "returnByValue": True}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == 1:
            ws.sock.close()
            check(f"TV Tools GPU = {mode}", msg["result"]["result"].get("value") == mode)
            time.sleep(2)
            return


def main(bid):
    print("## 1. clean state, normal start, close by webOS: GPU on", flush=True)
    tv(f"rm -f {ST}")
    check("GPU on", start()); close()
    check("no record", state() == "(none)")

    print("## 2. a recorded crash, then a run closed by webOS: GPU on, record cleared", flush=True)
    tv(f"printf '%s\\n%s\\n' '{bid}' 'crash (manual)' > {ST}")
    check("GPU on", start()); close()
    check("record cleared", state() == "(none)")

    print("## 3. one crash: GPU stays on, early-exit.log written", flush=True)
    start(); segv()
    check(f"record 'crash' ({state()})", state().startswith("crash"))
    check("early-exit.log written", tv(f"head -1 {EE} 2>/dev/null").startswith("status"))
    check("GPU on at the next start", start())

    print("## 4. second crash: GPU off, toast", flush=True)
    segv()
    check(f"record 'bad' ({state()})", state().startswith("bad"))
    check("toast sent", tv(f"grep -c 'toast sent' {LOG} || true").strip() != "0")
    check("GPU off at the next start", not start())

    print("## 5. TV Tools On: GPU on, record deleted, a crash does not count", flush=True)
    tvtools_gpu("on"); close()
    check("GPU on", start())
    check("record deleted", state() == "(none)")
    check("override logged", tv(f"grep -c '^run.sh gpu: on' {LOG} || true").strip() != "0")
    segv()
    check("forced run not counted", state() == "(none)")

    print("## 6. TV Tools Off: GPU off, a crash does not count", flush=True)
    start(); tvtools_gpu("off"); close()
    check("GPU off", not start())
    segv()
    check("forced run not counted", state() == "(none)")

    print("## 7. back on Auto: GPU on", flush=True)
    start(); tvtools_gpu("auto"); close()
    check("GPU on", start()); close()
    print("done", flush=True)


if __name__ == "__main__":
    if sys.argv[1:] != ["--yes"]:
        sys.exit(__doc__)
    if tv(f"grep -c -E '(^|[[:space:]])gpu=(on|off)([[:space:]]|$)' {T}/media.opts 2>/dev/null || true").strip() not in ("", "0"):
        sys.exit("media.opts sets gpu=on/off: the launcher's own check is skipped, remove it first")
    bid = tv(f"grep -a -o -E '[A-Z][a-z]{{2}} [ 0-9][0-9] [0-9]{{4}} [0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}' {A}/bin/run | head -1").strip()
    print("launcher build id:", bid, flush=True)
    try:
        main(bid)
    finally:
        uilat.fire(uilat.close_all())
        time.sleep(3)
        tv(f": > {T}/browser.flags; rm -f {ST}")
