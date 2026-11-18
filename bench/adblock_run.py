#!/usr/bin/env python3
"""Adblocker comparison in cr151b (own build + patch 0104, which lets MV2 extensions run): no blocker, uBlock Origin
Lite (MV3) in its optimal and complete modes, full uBlock Origin (MV2). Extensions come from --load-extension in
browser.flags (unpacked copies of the official release zips in the app's data folder, ab/{ubol,ubo}).
Every run is a fresh launch on a small local page; the case's page is then opened in that tab, so the uBO Lite mode
can be set first (its default mode lives in the extension's storage, and both uBOL variants share one copy).
usage: adblock_run.py <rounds> <case>...          cases: load-wiki speedometer (harness beacons), news (live page)
       adblock_run.py score <variant>...          adblock-tester.com result text
       adblock_run.py youtube <variant> <video id>...   ad shown or not, playback progress
       adblock_run.py warm <variant>...           one long launch, WARM_S seconds (default 90): uBO compiles its
                                                  lists on the first start and fetches list updates minutes later
       adblock_run.py tabs <variant>...           heavy pages one tab at a time until a tab or the browser dies
variants: none ubolopt ubolcomp ubo. Needs TV_HOST, tcprelay <TV LAN ip> 9226 -> 9225, lighttpd (bench/lighttpd.conf).
"""
import hashlib
import json
import os
import sys
import time
import urllib.request

import bench
import harness_run
import uilat
from inspector import WebSocket

APP_TAG = "cr151b"
uilat.APPS[APP_TAG] = "com.viiees.cr151b"
# The app's data folder: the browser runs in a jail that sees it, and it is where run.sh keeps TV Tools. run.sh passes
# its own --load-extension=<TV Tools>, and the last switch wins, so ours repeats TV Tools in the list.
DATA = "/media/developer/apps/usr/palm/applications/com.viiees.cr151b/data"
EXT = f"{DATA}/ab"
# run.sh caps every V8 heap at 192 MB (--js-flags="--max-old-space-size=192 --optimize-for-size"), and uBO's
# background page dies there ("V8 javascript OOM (Reached heap limit)" ~2 min after start). Every variant gets 320 MB
# so they stay comparable; browser.flags cannot carry a space inside a value, so --optimize-for-size drops out.
HEAP = "--js-flags=--max-old-space-size=320"
uilat.VARIANTS["heap"] = HEAP
uilat.VARIANTS["ubol"] = f"--load-extension={DATA}/ext/tvtools,{EXT}/ubol {HEAP}"
uilat.VARIANTS["ubo"] = f"--load-extension={DATA}/ext/tvtools,{EXT}/ubo {HEAP}"
# variant -> (browser.flags variant, uBO Lite default filtering mode: 2 optimal, 3 complete)
VARIANTS = {"none": ("heap", None), "ubolopt": ("ubol", 2), "ubolcomp": ("ubol", 3), "ubo": ("ubo", None)}
START_PAGE = f"{bench.HTTP}/pages/spatnav.html"
# Ad-heavy news front page (UK edition: the TV is in the UK). Live, so its own variance is part of the result.
NEWS = "https://www.dailymail.co.uk/home/index.html"
# Child processes rewrite their command line as one string (no NULs), so the switches are matched anywhere in it.
RSS = r"""for p in $(pidof chrome); do
  printf '%s %s ' $p $(awk '/VmRSS/ {print $2}' /proc/$p/status)
  tr '\0' ' ' < /proc/$p/cmdline | grep -o -E -- '--type=[a-z-]+|--extension-process' | tr '\n' ' '; echo
done"""


def unpacked_id(path):
    """Chrome's id of an unpacked extension: sha256 of its path, first 32 hex digits mapped to a-p."""
    return "".join(chr(ord("a") + int(c, 16)) for c in hashlib.sha256(path.encode()).hexdigest()[:32])


def targets():
    return json.load(urllib.request.urlopen(f"http://{uilat.CDP}/json/list", timeout=20))


def evaluate(target_id, expr, await_promise=False, user_gesture=False):
    ws = WebSocket(uilat.CDP, "/devtools/page/" + target_id)
    ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {
        "expression": expr, "returnByValue": True, "awaitPromise": await_promise, "userGesture": user_gesture}}))
    try:
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                result = msg.get("result", {})
                if "exceptionDetails" in result:
                    raise RuntimeError(f"{expr[:60]}: {result['exceptionDetails'].get('text')}")
                return result.get("result", {}).get("value")
    finally:
        ws.sock.close()


def page_target():
    return next(t for t in targets() if t["type"] == "page" and t["url"].startswith("http"))


def page_eval(expr, **kw):
    return evaluate(page_target()["id"], expr, **kw)


def launch(variant):
    """Fresh launch with the variant's extension; sets the uBO Lite mode; leaves only the start page open."""
    flag, mode = VARIANTS[variant]
    br = uilat.start(f"{APP_TAG}+{flag}" if flag else APP_TAG, START_PAGE)
    if mode is not None:
        url = f"chrome-extension://{unpacked_id(EXT + '/ubol')}/dashboard.html"
        tid = br.call("Target.createTarget", {"url": url, "background": True})["targetId"]
        time.sleep(3)
        got = evaluate(tid, f"chrome.runtime.sendMessage({{what: 'setDefaultFilteringMode', level: {mode}}})",
                       await_promise=True)
        if got != mode:
            raise RuntimeError(f"uBO Lite mode {got}, wanted {mode}")
        br.call("Target.closeTarget", {"targetId": tid})
    for t in targets():   # first-run pages of the extensions would take the foreground
        if t["type"] == "page" and not t["url"].startswith("http"):
            br.call("Target.closeTarget", {"targetId": t["id"]})
    br.call("Target.activateTarget", {"targetId": page_target()["id"]})
    return br


def rss():
    """VmRSS in kB: the browser process, the extension process(es), and all chrome processes."""
    browser = ext = total = 0
    for line in bench.tv(RSS).splitlines():
        parts = line.split()
        if len(parts) < 2 or not parts[1].isdigit():
            continue
        kb = int(parts[1])
        total += kb
        if len(parts) == 2:
            browser += kb
        elif "--extension-process" in parts:
            ext += kb
    return f"rss_browser_kb={browser} rss_ext_kb={ext} rss_total_kb={total}"


def open_url(url):
    page_eval(f"location.href = {json.dumps(url)}")


NEWS_WINDOW_S = 60


def news(variant, run):
    """The ad-heavy page never fires load on this TV (ads keep loading), so it is measured over a fixed window from
    CDP Network events: DOMContentLoaded, requests finished and their bytes, requests failed (blocked included).
    Resource Timing would not do: its 250-entry buffer fills on this page."""
    ws = WebSocket(uilat.CDP, "/devtools/page/" + page_target()["id"])
    for i, method in enumerate(("Network.enable", "Page.enable"), 1):
        ws.send(json.dumps({"id": i, "method": method}))
    ws.send(json.dumps({"id": 3, "method": "Page.navigate", "params": {"url": NEWS}}))
    start, stats = time.time(), {"dcl_ms": 0, "load_ms": 0, "requests": 0, "finished": 0, "kb": 0, "failed": 0,
                                 "blocked": 0}
    ws.sock.settimeout(1)
    deadline = start + NEWS_WINDOW_S
    try:
        while time.time() < deadline:
            try:
                m = json.loads(ws.recv())
            except OSError:   # socket.timeout is an OSError
                continue
            method, p = m.get("method"), m.get("params", {})
            if method == "Network.requestWillBeSent":
                stats["requests"] += 1
            elif method == "Network.loadingFinished":
                stats["finished"] += 1
                stats["kb"] += p.get("encodedDataLength", 0) / 1024
            elif method == "Network.loadingFailed":
                stats["failed"] += 1
                stats["blocked"] += bool(p.get("blockedReason") or "BLOCKED_BY_CLIENT" in p.get("errorText", ""))
            elif method == "Page.domContentEventFired" and not stats["dcl_ms"]:
                stats["dcl_ms"] = round((time.time() - start) * 1000)
            elif method == "Page.loadEventFired" and not stats["load_ms"]:
                stats["load_ms"] = round((time.time() - start) * 1000)
    finally:
        ws.sock.close()
    stats["kb"] = round(stats["kb"])
    mem = rss()
    fields = " ".join(f"{k}={v}" for k, v in stats.items())
    print(f"{variant} news #{run}: window_s={NEWS_WINDOW_S} {fields} {mem}", flush=True)


def harness(variant, case, run):
    open_url(f"{bench.HTTP}/pages/harness.html?case={case}&tag={variant}&run={run}")
    deadline = time.time() + harness_run.CEILING[case]
    got = None
    while time.time() < deadline and not got:
        time.sleep(5)
        got = harness_run.beacon(variant, case, run)
    mem = rss()
    got = got or {"timeout": "1"}
    for k in ("ua", "tag", "case", "run"):
        got.pop(k, None)
    print(f"{variant} {case} #{run}: " + " ".join(f"{k}={v}" for k, v in got.items()) + f" {mem}", flush=True)


def reject_consent():
    """Google's EU/UK consent page: take the least-sharing choice ("Reject all")."""
    return page_eval("""(() => { const b = [...document.querySelectorAll("button")]
        .find(e => /reject all/i.test(e.textContent)); if (b) { b.click(); return true; } return false; })()""",
                     user_gesture=True)


def youtube(variant, ids):
    for vid in ids:
        open_url(f"https://www.youtube.com/watch?v={vid}")
        time.sleep(8)
        if reject_consent():
            time.sleep(8)
        # the TV blocks autoplay with sound: start it as a click would
        page_eval("(v => { if (v) v.play().catch(() => {}); return !!v; })(document.querySelector('video'))",
                  user_gesture=True)
        samples = []
        for _ in range(20):   # 60 s: a pre-roll and the start of the video
            time.sleep(3)
            try:
                # after a pre-roll the video waits paused at 0: press play again, as a viewer would
                page_eval("""(() => { const p = document.querySelector("#movie_player"),
                    v = document.querySelector("video");
                    if (v && v.paused && !(p && p.classList.contains("ad-showing"))) v.play().catch(() => {}); })()""",
                          user_gesture=True)
                samples.append(page_eval("""(() => { const p = document.querySelector("#movie_player"),
                    v = document.querySelector("video");
                    return [p ? p.classList.contains("ad-showing") : null, v ? Math.round(v.currentTime) : null,
                            v ? v.paused : null, v ? Math.round(v.duration) : null,
                            !!document.querySelector(".ytp-error")]; })()"""))
            except Exception as e:
                samples.append(str(e)[:40])
        ok = [s for s in samples if isinstance(s, list)]
        ads = sum(1 for s in ok if s[0])
        played = max((s[1] for s in ok if not s[0] and s[1] is not None), default=0)
        print(f"{variant} youtube {vid}: ad_samples={ads}/{len(samples)} video_played_s={played} "
              f"errors={sum(1 for s in ok if s[4])} first={ok[0] if ok else None} last={ok[-1] if ok else None}",
              flush=True)


def score(variant):
    open_url("https://adblock-tester.com/")
    time.sleep(60)
    shot = f"/tmp/abt_{variant}.png"
    bench.tv(f"luna-send -n 1 luna://com.webos.service.capture/executeOneShot "
             f"'{{\"path\":\"{shot}\",\"method\":\"DISPLAY\",\"format\":\"PNG\",\"width\":1920,\"height\":1080}}'")
    # the site's own result element, and the service names whose checks failed ("<check>: ❌ test failed" lines)
    try:
        text = page_eval("""(() => { const s = document.querySelector(".final-score"),
            lines = document.body.innerText.split("\\n"), failed = new Set();
            let service = "";
            for (const l of lines) { if (!/test (passed|failed)|:\\s/.test(l) && l.trim()) service = l.trim();
                                     if (/test failed/.test(l)) failed.add(service); }
            return (s ? s.textContent.trim() : "no score element") + " | failed: " + [...failed].join(", "); })()""")
    except Exception as e:
        text = f"no answer from the page ({type(e).__name__}), see {shot}"
    print(f"{variant} adblock-tester: {' '.join((text or '').split())!r}", flush=True)


# Heavy public pages, no login. Consent walls are left as they are: the same for every variant.
TAB_SITES = ("https://www.dailymail.co.uk/home/index.html", "https://www.theguardian.com/uk",
             "https://www.bbc.co.uk/news", "https://edition.cnn.com/", "https://www.independent.co.uk/",
             "https://www.mirror.co.uk/", "https://en.wikipedia.org/wiki/United_States", "https://www.ebay.co.uk/",
             "https://www.reddit.com/r/popular/", "https://www.thesun.co.uk/")
TAB_STEP_S = 45
TAB_MAX = int(os.environ.get("TAB_MAX", 20))
MEMINFO = "grep -E '^(MemAvailable|SwapTotal|SwapFree):' /proc/meminfo | tr -s ' ' | tr '\\n' ' '"


def tab_alive(target_id):
    """'ok', 'busy' (no answer in 20 s: a renderer still loading a heavy page), 'crashed', or another failure."""
    try:
        ws = WebSocket(uilat.CDP, "/devtools/page/" + target_id)
    except Exception as e:
        return f"noconnect:{type(e).__name__}"
    ws.sock.settimeout(20)
    try:
        ws.send(json.dumps({"id": 1, "method": "Inspector.enable"}))
        ws.send(json.dumps({"id": 2, "method": "Runtime.evaluate", "params": {"expression": "1+1", "returnByValue": True}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("method") == "Inspector.targetCrashed":
                return "crashed"
            if msg.get("id") == 2:
                if "error" in msg:
                    return "error:" + msg["error"].get("message", "")[:40].replace(" ", "_")
                return "ok" if msg.get("result", {}).get("result", {}).get("value") == 2 else "error"
    except OSError:
        return "busy"
    finally:
        ws.sock.close()


def browser_pid():
    """The oldest chrome process is the browser; the trailing space skips chrome_crashpad_handler."""
    return bench.tv("pgrep -o -f 'cr151b/browser/chrome '").strip()


def tabs(variant, br):
    """Open heavy pages one tab at a time until the browser or a tab dies, or TAB_MAX tabs. One line per step."""
    pid = browser_pid()
    for n in range(1, TAB_MAX + 1):
        try:
            br.call("Target.createTarget", {"url": TAB_SITES[(n - 1) % len(TAB_SITES)]})
        except Exception as e:
            print(f"{variant} tabs: browser gone at tab {n} ({type(e).__name__})", flush=True)
            return
        time.sleep(TAB_STEP_S)
        now_pid = browser_pid()
        try:
            pages = [t for t in targets() if t["type"] == "page" and t["url"].startswith("http")]
        except Exception:
            pages = []
        states = [tab_alive(t["id"]) for t in pages]
        bad = len(states) - states.count("ok") - states.count("busy")
        mem = " ".join(bench.tv(MEMINFO).split())
        print(f"{variant} tabs n={n} pages={len(pages)} ok={states.count('ok')} busy={states.count('busy')} bad={bad} "
              f"pid_same={int(now_pid == pid and bool(pid))} {mem} {rss()}", flush=True)
        if now_pid != pid or bad or len(pages) < n:
            print(f"{variant} tabs: first failure at tab {n}: {states}", flush=True)
            return
    print(f"{variant} tabs: survived {TAB_MAX} tabs", flush=True)


def main():
    bench.tv("wget -q -O /dev/null http://127.0.0.1:8099/pages/spatnav.html || "
             "lighttpd -f /media/developer/bench/lighttpd.conf")
    # preloaded YouTube and the system browser hold memory and CPU (docs/FINDINGS.md); keep the run comparable
    uilat.fire("".join(f"luna-send -n 1 luna://com.webos.applicationManager/closeByAppId '{{\"id\":\"{a}\"}}' "
                       ">/dev/null; " for a in bench.BACKGROUND_APPS))
    args = sys.argv[1:]
    if args[0] in ("score", "youtube", "warm", "tabs"):
        variants = args[1:] if args[0] != "youtube" else args[1:2]
        for variant in variants:
            br = launch(variant)
            if args[0] == "tabs":
                tabs(variant, br)
            elif args[0] == "score":
                score(variant)
            elif args[0] == "youtube":
                youtube(variant, args[2:])
            else:
                time.sleep(int(os.environ.get("WARM_S", 90)))   # uBO updates its lists a few minutes in
                print(f"{variant} warm: {rss()}", flush=True)
            br.ws.sock.close()
            uilat.fire(uilat.close_all())
        return
    stamp = int(time.time()) % 100000
    for r in range(int(args[0])):
        for case in args[1:]:
            for variant in VARIANTS:
                br = launch(variant)
                if case == "news":
                    news(variant, f"{stamp}-{r}")
                else:
                    harness(variant, case, f"{stamp}-{r}")
                br.ws.sock.close()
                uilat.fire(uilat.close_all())


if __name__ == "__main__":
    main()
