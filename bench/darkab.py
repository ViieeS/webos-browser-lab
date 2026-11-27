"""Dark theme cost A/B in the owner's profile: TV Tools' darkTheme is switched before each run (run.sh reads it at
start) and rounds alternate on/off. Every run logs the launcher's gpu line, so a run in software mode shows. The
saved darkTheme is restored at the end. usage: darkab.py <rounds> <out>"""
import contextlib
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uilat
from inspector import WebSocket

uilat.SHOW = uilat.PREFIXES + ("Graphics.Smoothness.PercentDroppedFrames3.AllSequences",
                               "Graphics.Smoothness.PercentDroppedFrames3.MainThread")
TVT = "ikkplgnegbekkbamfelhaeahnaddgnma"
GET = "tvLoad().then(r => r.settings.darkTheme)"
SET = """tvLoad().then(r => { r.settings.darkTheme = "%s"; return tvSave(r.settings); })
  .then(() => chrome.storage.local.get("settings")).then(r => r.settings.darkTheme)"""


def tvtools(expression):
    """Evaluate in TV Tools' service worker of a fresh browser, then close the browser."""
    uilat.start("chromiumtv").ws.sock.close()
    sw = []
    for _ in range(10):
        targets = json.load(urllib.request.urlopen(f"http://{uilat.CDP}/json/list", timeout=20))
        sw = [t for t in targets if t["url"].startswith(f"chrome-extension://{TVT}/") and "worker" in t["type"]]
        if sw:
            break
        time.sleep(2)
    if not sw:
        raise RuntimeError("TV Tools service worker not found")
    ws = WebSocket(uilat.CDP, "/devtools/page/" + sw[0]["id"])
    ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                        "params": {"expression": expression, "awaitPromise": True, "returnByValue": True}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == 1:
            ws.sock.close()
            got = msg["result"]["result"].get("value")
            break
    time.sleep(2)   # LevelDB write
    uilat.fire(uilat.close_all())
    time.sleep(3)
    return got


def flags():
    return uilat.bench.tv("tr '\\0' ' ' < /proc/$(pidof chrome | tr ' ' '\\n' | sort -n | head -1)/cmdline | "
                          "grep -o 'WebContentsForceDark\\|force-dark-mode\\|disable-gpu' | sort -u | tr '\\n' ' '")


def gpu_line():
    return uilat.bench.tv("grep -h 'gpu:' /tmp/com.viiees.chromiumtv/media.log | tail -1").strip()


rounds, out = int(sys.argv[1]), sys.argv[2]
with open(out, "w") as f, contextlib.redirect_stdout(f):
    saved = tvtools(GET)
    if saved not in ("on", "sites", "off"):
        raise RuntimeError(f"unexpected saved darkTheme {saved!r}")
    print(f"### saved darkTheme before the run: {saved}", flush=True)
    try:
        for rnd in range(1, rounds + 1):
            for mode in (("on", "off") if rnd % 2 else ("off", "on")):
                print(f"### round {rnd} dark={mode}", flush=True)
                for scenario in ("keyscroll", "keyfocus"):
                    # Saved again before every run: run.sh reads the value reliably only while it is still in
                    # LevelDB's .log (FINDINGS, "TV Tools settings lost after one start").
                    saved_now = tvtools(SET % mode)
                    br = uilat.start("chromiumtv")
                    fl = flags()
                    ok = ("force-dark-mode" in fl) == (mode == "on")
                    print(f"dark={mode} {scenario} #{rnd} saved={saved_now} flags: {fl.strip()} "
                          f"{'' if ok else 'MISMATCH '}| {gpu_line()}", flush=True)
                    br.sync_children()
                    br.histograms(True)
                    uilat.press(uilat.SCENARIOS[scenario])
                    time.sleep(2)
                    br.sync_children()
                    print(f"dark={mode} {scenario} #{rnd}: {uilat.show(br.histograms(True), uilat.SHOW)}", flush=True)
                    br.ws.sock.close()
                    uilat.fire(uilat.close_all())
    finally:
        print(f"### restored darkTheme={tvtools(SET % saved)}", flush=True)
        uilat.bench.tv(": > /tmp/com.viiees.chromiumtv/browser.flags")
print("done")
