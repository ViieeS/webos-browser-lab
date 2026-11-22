#!/usr/bin/env python3
"""Input latency on heavy sites in Chromium TV: what makes the browser slow to answer the remote, across sites.
Per run: a fresh launch on the site, then remote keys through evdev (uilat.press path). Collected per run:
- Event Timing entries of every keydown: input delay, handler time, time to the next paint (Chrome rounds the
  duration to 8 ms and reports only entries of 16 ms and more), and whether the page called preventDefault (then
  spatial navigation does not run for that key);
- Long Animation Frames with script attribution;
- Chromium's EventLatency.KeyPressed.* histograms (renderer stage split);
- CPU time over the key sequence: every chrome process by type, the busiest threads by name, the whole TV;
- swap traffic (pswpin/pswpout) and MemAvailable/SwapFree, since zram is the TV's only reserve.
usage: inputlat.py run <tag>[,<tag>...] <rounds> <site>[,<site>...]
       inputlat.py settings <tag> get | set '<json merged into TV Tools settings>' | restore <file>
tag = app[+variant][@profile]: app from uilat.APPS (chromiumtv), variant from VARIANTS (browser.flags, the last switch
wins over run.sh), profile from PROFILES (TV Tools settings; the stored settings are read first and written back after
the run). Needs TV_HOST, tcprelay <TV LAN ip> 9226 -> 9225, /media/developer/temp/evkeys, keepawake.sh.
"""
import json
import sys
import time
import traceback
import urllib.request

import adblock_run
import bench
import uilat
from inspector import WebSocket

UP, LEFT, RIGHT, DOWN = 103, 105, 106, 108
# (url, gap between presses in ms, keys). Keys a viewer uses: arrows; OK opens things (a video, an article) and would
# leave the page, so it is not part of the sequence.
SITES = {
    # YouTube. With TV Tools' TV user agent youtube.com/tv now redirects to the desktop site (/?app=desktop): a large
    # JS app either way
    "yt": ("https://www.youtube.com/tv", 500, [RIGHT] * 8 + [DOWN] * 4 + [RIGHT] * 6 + [UP] * 4 + [LEFT] * 6),
    # a held Right on YouTube: as fast as the remote's auto-repeat
    "ythold": ("https://www.youtube.com/tv", 150, [RIGHT] * 20 + [LEFT] * 20),
    # SPA with a big JS bundle and an endless feed
    "reddit": ("https://www.reddit.com/r/popular/", 500, [DOWN] * 24 + [UP] * 6),
    # a long news front page with ads and many images
    "news": ("https://www.dailymail.co.uk/home/index.html", 500, [DOWN] * 24 + [UP] * 6),
    # a WebGL map, arrows pan it
    "maps": ("https://www.google.com/maps/@51.5072,-0.1276,14z", 500, [RIGHT] * 8 + [DOWN] * 8 + [LEFT] * 8 + [UP] * 6),
}
# The owner's own input: the Magic Remote wheel and pointer, keys only now and then.
# Wheel: evkeys into the Magic Remote's own node (event3, "LGE M-RCU"); event10 passes keys only. "a<x>,<y>" sets the
# pointer in screen pixels, "r8:-1" is one wheel notch down (deltaY 120, 120 px), "w<ms>" a pause. A person spins the
# wheel in bursts of notches ~80 ms apart. The pointer goes to the middle first, so the wheel scrolls the page.
WHEEL_DEV = "/dev/input/event3"
CENTER = "a960,540"
WHEEL = [CENTER, "w1000"] + ["r8:-1"] * 12 + ["w1500"] + ["r8:-1"] * 12 + ["w1500"] + ["r8:1"] * 6
# Pointer: surface-manager takes injected ABS moves but sends no wl_pointer motion for them (a real remote turns the
# cursor on somehow; the position arrives only with the next wheel event). So the sweep goes in through CDP
# Input.dispatchMouseEvent in CSS pixels of the 1272x595 viewport, every 10 ms like the remote's ~100 Hz reports:
# the renderer's hover work is the same, the Wayland hop is skipped.
HOVER = [f"a{x},{y}" for y in (120, 300, 480) for x in range(40, 1240, 30)]
for _name in ("yt", "reddit", "news", "maps"):
    SITES[_name + "-wheel"] = (SITES[_name][0], 80, WHEEL)
    SITES[_name + "-hover"] = (SITES[_name][0], 10, HOVER)
# YouTube's home is an empty, unscrollable page without a watch history: wheel and hover use a results list.
YT_LIST = "https://www.youtube.com/results?search_query=4k+nature"
SITES["yt-wheel"] = (YT_LIST, 80, WHEEL)
SITES["yt-hover"] = (YT_LIST, 10, HOVER)
# a long, light article: the floor for wheel scrolling
SITES["wiki-wheel"] = ("https://en.wikipedia.org/wiki/Television", 80, WHEEL)
# The same notches through CDP Input.dispatchMouseEvent instead of evdev: Chrome stamps them itself, so the scroll
# jank metrics see no webOS input timestamps. "c8:-1" is one notch down, at the middle of the 1272x595 viewport.
CDP_WHEEL = ["w1000"] + ["c8:-1"] * 12 + ["w1500"] + ["c8:-1"] * 12 + ["w1500"] + ["c8:1"] * 6
SITES["wiki-cdpwheel"] = (SITES["wiki-wheel"][0], 80, CDP_WHEEL)
# One long synthetic scroll per gesture (CDP Input.synthesizeScrollGesture, mouse source): many frames in one scroll,
# like the latched evdev notches, but with timestamps Chrome makes itself. "g<px>:<px per s>", negative px = down.
SITES["wiki-cdpgesture"] = (SITES["wiki-wheel"][0], 80, ["w1000", "g-1440:800", "w1500", "g-1440:800", "w1500", "g720:800"])


def inputs(tokens):
    """(kind, count) of a token list: keys (keydown), wheel notches, or pointer moves (hover)."""
    notches = sum(1 for t in tokens if str(t).startswith("r8:"))
    if any(str(t).startswith("g") for t in tokens):
        return "cdpwheel", sum(1 for t in tokens if str(t).startswith("g"))
    cdp_notches = sum(1 for t in tokens if str(t).startswith("c8:"))
    if cdp_notches:
        return "cdpwheel", cdp_notches
    moves = sum(1 for t in tokens if str(t).startswith("a"))
    keys = sum(1 for t in tokens if isinstance(t, int) or str(t)[0].isdigit())
    return ("wheel", notches) if notches else ("key", keys) if keys else ("hover", moves)
uilat.VARIANTS.update({
    "rpl4": "--renderer-process-limit=4",
    "nolowend": "--disable-low-end-device-mode",
    "raster2": "--num-raster-threads=2",
    "nogpuraster": "--disable-gpu-rasterization",
    # run.sh: --max-old-space-size=192 --optimize-for-size --sqrt-allocation-limits. browser.flags is word-split, so
    # a --js-flags value cannot hold a space: this drops the heap cap and optimize-for-size together.
    "jsfull": "--js-flags=--sqrt-allocation-limits",
    # TV Tools alone: Chrome keeps the last --load-extension. run.sh's one lists TV Tools and uBO Lite, and since
    # IPK c9a7b84c also autoconsent, so on that build this variant drops autoconsent too.
    "noubol": "--load-extension=/media/developer/apps/usr/palm/applications/com.viiees.chromiumtv/data/ext/tvtools",
})
# Changes made on the TV after the launch instead of by a flag (see hooks below).
HOOKS = {"prio"}
# run.sh switches that have no negating switch: the variant drops the switch from the installed run.sh for that one
# launch. The file is copied to run.sh.ab first and put back after the run (and at the next start if a run died).
RUNSH = "/media/developer/apps/usr/palm/applications/com.viiees.chromiumtv/bin/run.sh"
RUNSH_DROP = {"gpuproc": "--in-process-gpu", "noppsite": "--process-per-site", "smooth": "--disable-smooth-scrolling"}
PROFILES = {"lite": {"lite": True}}

OBSERVE = """(() => { const r = window.__il = {ev: [], other: [], loaf: [], prevented: [], got: 0,
    n: {wheel: 0, mousemove: 0, mouseover: 0, scroll: 0}, t0: performance.now()};
  // Event Timing has no wheel or mousemove entries: for the wheel the page side is the scroll events and LoAF, the
  // browser side the GestureScroll EventLatency histograms. Hover shows up as mouseover/pointerover entries.
  new PerformanceObserver(l => { for (const e of l.getEntries()) (e.name === "keydown" ? r.ev : r.other).push(
    e.name === "keydown" ? [e.startTime, e.processingStart, e.processingEnd, e.duration]
                         : [e.name, e.startTime, e.processingStart, e.processingEnd, e.duration]); })
    .observe({type: "event", durationThreshold: 16});
  for (const t of Object.keys(r.n)) addEventListener(t, () => r.n[t]++, {capture: true, passive: true});
  r.wheelT = []; addEventListener("wheel", e => r.wheelT.push([Math.round(e.timeStamp), Math.round(scrollY)]),
    {capture: true, passive: true});
  // The frame rhythm the page sees: rAF time and scroll position, an independent check of the EventLatency totals.
  r.raf = []; const tick = t => { if (r.raf.length < 4000) { r.raf.push([Math.round(t), Math.round(scrollY)]);
    requestAnimationFrame(tick); } }; requestAnimationFrame(tick);
  new PerformanceObserver(l => { for (const e of l.getEntries()) r.loaf.push({t: e.startTime, d: e.duration,
    block: e.blockingDuration, layout: e.styleAndLayoutStart ? e.startTime + e.duration - e.styleAndLayoutStart : 0,
    scripts: e.scripts.map(s => [s.invoker, s.sourceFunctionName, (s.sourceURL || "").replace(/^https?:\\/\\//, "").replace(/\\/.*\\//, "/").slice(0, 60),
                                 Math.round(s.duration), Math.round(s.forcedStyleAndLayoutDuration)])}); })
    .observe({type: "long-animation-frame"});
  addEventListener("keydown", () => r.got++, true);   // capture: every key that reached the page, stopped or not
  addEventListener("keydown", e => r.prevented.push(e.defaultPrevented));   // bubble phase, after the page's handlers
  return true; })()"""
COLLECT = "JSON.stringify(window.__il)"
PAGE_INFO = """JSON.stringify({url: location.href, ua: navigator.userAgent,
  nodes: document.getElementsByTagName("*").length, scrollY: Math.round(scrollY),
  heapMB: performance.memory ? +(performance.memory.usedJSHeapSize / 1048576).toFixed(1) : null,
  focused: document.activeElement ? document.activeElement.tagName : null})"""


def page_eval(expr):
    """uilat.page_eval, waiting out a redirect: while a site moves to another host (dailymail.co.uk -> .com) the
    tab has no http target for a moment."""
    for _ in range(15):
        try:
            return uilat.page_eval(expr)
        except StopIteration:
            time.sleep(2)
    targets = json.load(urllib.request.urlopen(f"http://{uilat.CDP}/json/list", timeout=20))
    raise RuntimeError(f"no http page target for 30 s: {[(t['type'], t['url'][:60]) for t in targets]}")


def extension_eval(expr, worker="/bg.js"):
    """Evaluates in an extension's service worker, where chrome.storage is available: TV Tools' bg.js by default,
    uBO Lite's is /js/background.js."""
    targets = json.load(urllib.request.urlopen(f"http://{uilat.CDP}/json/list", timeout=20))
    sw = next(t for t in targets if t["type"] == "service_worker" and t["url"].endswith(worker))
    ws = WebSocket(uilat.CDP, "/devtools/page/" + sw["id"])
    ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                        "params": {"expression": expr, "returnByValue": True, "awaitPromise": True}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == 1:
            ws.sock.close()
            return msg["result"]["result"].get("value")


def settings_get():
    """The stored settings object as JSON text, "null" when the profile never saved any."""
    value = extension_eval("chrome.storage.local.get('settings').then(r => JSON.stringify(r.settings || null))")
    assert value is not None, "TV Tools service worker did not answer"
    return value


def settings_put(value_json):
    expr = (f"(v => v === null ? chrome.storage.local.remove('settings') : chrome.storage.local.set({{settings: v}}))"
            f"({value_json}).then(() => chrome.storage.local.get('settings')).then(r => JSON.stringify(r.settings || null))")
    return extension_eval(expr)


def wait_ready(site, seconds=60):
    """readyState complete (on YouTube also its app element: the page shell completes before the app)."""
    check = ("document.readyState === 'complete' && !!document.querySelector('ytd-app, ytlr-app')"
             if site.startswith("yt") else "document.readyState === 'complete'")
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if page_eval(check):
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def snapshot():
    """One telnet round: every chrome thread's ticks with its process type and name, /proc/stat cpu, swap, memory."""
    out = bench.tv(
        "head -1 /proc/stat; grep -E '^pswp' /proc/vmstat; sed 's/^/P /' /proc/[0-9]*/stat 2>/dev/null; "
        " grep -E '^(MemAvailable|SwapFree):' /proc/meminfo; "
        "for p in $(pidof chrome); do t=$(tr '\\0' ' ' < /proc/$p/cmdline | grep -o -- '--type=[a-z-]*'); "
        "for k in /proc/$p/task/*; do echo T $p ${t:-browser} $(cut -d' ' -f14,15,18 $k/stat) $(cat $k/comm | tr ' ' _); "
        "done; done")
    snap = {"threads": {}, "procs": {}}
    for line in out.splitlines():
        f = line.split()
        if not f:
            continue
        if f[0] == "P" and ") " in line:   # every process on the TV: "P pid (comm) state ppid ... utime stime"
            pid, rest = line[2:].split(" (", 1)
            comm, tail = rest.rsplit(") ", 1)
            t = tail.split()
            snap["procs"][f"{comm}:{pid}"] = int(t[11]) + int(t[12])
        elif f[0] == "cpu":
            snap["total"], snap["idle"] = sum(int(x) for x in f[1:]), int(f[4])
        elif f[0] in ("pswpin", "pswpout"):
            snap[f[0]] = int(f[1])
        elif f[0] in ("MemAvailable:", "SwapFree:"):
            snap[f[0][:-1]] = int(f[1]) // 1024
        elif f[0] == "T" and len(f) >= 7:
            pid, kind, ut, st, nice, name = f[1], f[2].replace("--type=", ""), f[3], f[4], f[5], f[6]
            snap["threads"][(pid, name, len(snap["threads"]))] = (kind, int(ut) + int(st), int(nice))
    return snap


def cpu_delta(a, b):
    """CPU ms by process type and by thread (type/name), from two snapshots (thread keys may differ: new threads)."""
    def by_name(s):
        acc = {}
        for (pid, name, _), (kind, ticks, nice) in s["threads"].items():
            k = f"{kind}/{name}"
            acc[k] = acc.get(k, 0) + ticks
        return acc
    na, nb = by_name(a), by_name(b)
    threads = {k: (nb[k] - na.get(k, 0)) * 10 for k in nb if nb[k] - na.get(k, 0) > 0}
    types = {}
    for k, ms in threads.items():
        types[k.split("/")[0]] = types.get(k.split("/")[0], 0) + ms
    nice = sorted({f"{kind}/{name}:{n}" for (pid, name, _), (kind, t, n) in b["threads"].items()
                   if name.startswith(("CrRendererMain", "CrBrowserMain", "Compositor", "VizCompositor", "Chrome_InProc"))})
    procs = {k: (b["procs"][k] - a["procs"].get(k, 0)) * 10 for k in b["procs"]
             if not k.startswith("chrome:") and b["procs"][k] - a["procs"].get(k, 0) > 0}
    return {"ms_by_type": types, "top_threads": dict(sorted(threads.items(), key=lambda x: -x[1])[:12]),
            "top_other_procs": dict(sorted(procs.items(), key=lambda x: -x[1])[:10]),
            "ms_all_tv_cpus": ((b["total"] - a["total"]) - (b["idle"] - a["idle"])) * 10,
            "ms_wall_x4": (b["total"] - a["total"]) * 10, "nice": nice,
            "swap_pages_in": b.get("pswpin", 0) - a.get("pswpin", 0),
            "swap_pages_out": b.get("pswpout", 0) - a.get("pswpout", 0),
            "mem_avail_mb": b.get("MemAvailable"), "swap_free_mb": b.get("SwapFree")}


def hook_prio():
    """run.sh puts every Chrome thread except compositor, GPU and media back to nice 0 (webOS gives the foreground app
    -8) every 3 s. This stops run.sh's background subshells (that loop, the memory log, the hw.json watcher: all are
    sh processes with chromiumtv's bin/run.sh in their command line) and gives every Chrome thread -8 again."""
    print("  prio: " + bench.tv(
        "for s in /proc/[0-9]*; do [ \"$(cat $s/comm 2>/dev/null)\" = sh ] && "
        "tr '\\0' ' ' < $s/cmdline | grep -q 'chromiumtv/bin/run.sh' && kill ${s##*/} && echo killed ${s##*/}; done; "
        "for p in $(pidof chrome); do for k in /proc/$p/task/*; do renice -8 -p ${k##*/} >/dev/null 2>&1; done; done; "
        "echo reniced").strip().replace("\n", " "), flush=True)


def runsh_restore():
    """Puts the installed run.sh back from run.sh.ab. Fails loudly: a TV left with an edited run.sh is the one
    outcome the owner must hear about."""
    out = bench.tv(f"[ -f {RUNSH}.ab ] || {{ echo none; exit; }}; cp -p {RUNSH}.ab {RUNSH} && cmp {RUNSH}.ab {RUNSH} "
                   f"&& rm {RUNSH}.ab && echo restored")
    if "none" not in out and "restored" not in out:
        raise RuntimeError(f"run.sh not restored: {out}")
    return out.strip()


def runsh_drop(switch):
    out = bench.tv(f"[ -f {RUNSH}.ab ] || cp -p {RUNSH} {RUNSH}.ab; sed -i 's| {switch} | |' {RUNSH}; "
                   f"grep -c -- ' {switch} ' {RUNSH}")
    if out.strip().splitlines()[-1] != "0":
        raise RuntimeError(f"{switch} still in run.sh: {out}")


def run(tag, site, rnd):
    app, _, profile = tag.partition("@")
    base, _, variant = app.partition("+")
    flag_variant = variant if variant not in HOOKS | RUNSH_DROP.keys() else ""
    url = SITES[site][0]
    if variant in RUNSH_DROP:
        runsh_drop(RUNSH_DROP[variant])
    try:
        br = uilat.start(f"{base}+{flag_variant}" if flag_variant else base, url)
    finally:   # run.sh is read once at the launch, so it goes back before the measurement
        if variant in RUNSH_DROP:
            print(f"  run.sh: {runsh_restore()}", flush=True)
    saved = None
    try:
        if profile:   # the settings apply to requests from now on: load the page again
            saved = settings_get()
            settings_put(json.dumps({**json.loads(saved), **PROFILES[profile]}))
            page_eval("location.reload()")
            time.sleep(5)
        if variant == "prio":
            hook_prio()
        measure(br, tag, site, rnd)
    finally:
        if saved is not None:   # the owner's own settings back, exactly as stored
            print(f"  settings restored: {settings_put(saved)}", flush=True)
        uilat.fire(uilat.close_all())


def cdp_pointer(tokens, gap):
    """Mouse moves through CDP on the page target, one per gap; the replies are read after the sweep, so a busy main
    thread does not slow the sender down (a real remote does not wait either). Also takes CDP_WHEEL's tokens:
    "c8:<n>" is one wheel notch (n=-1 down), "w<ms>" a pause."""
    page = None
    for _ in range(15):
        targets = json.load(urllib.request.urlopen(f"http://{uilat.CDP}/json/list", timeout=20))
        page = next((t for t in targets if t["type"] == "page" and t["url"].startswith("http")), None)
        if page:
            break
        time.sleep(2)
    assert page, f"no http page target: {[(t['type'], t['url'][:60]) for t in targets]}"
    ws = WebSocket(uilat.CDP, "/devtools/page/" + page["id"])
    sent = 0
    for t in tokens:
        if t.startswith("w"):
            time.sleep(int(t[1:]) / 1000)
            continue
        if t.startswith("g"):
            px, speed = map(int, t[1:].split(":"))
            sent += 1
            ws.send(json.dumps({"id": sent, "method": "Input.synthesizeScrollGesture", "params": {
                "x": 636, "y": 297, "yDistance": px, "speed": speed, "gestureSourceType": "mouse"}}))
            time.sleep(abs(px) / speed + 0.3)
            continue
        if t.startswith("c8:"):
            params = {"type": "mouseWheel", "x": 636, "y": 297, "deltaX": 0, "deltaY": -120 * int(t[3:])}
        else:
            x, y = map(int, t[1:].split(","))
            params = {"type": "mouseMoved", "x": x, "y": y}
        sent += 1
        ws.send(json.dumps({"id": sent, "method": "Input.dispatchMouseEvent", "params": params}))
        time.sleep(gap / 1000)
    done = 0
    while done < sent:
        if "id" in json.loads(ws.recv()):
            done += 1
    ws.sock.close()


def ensure_page(url):
    """The luna launch sometimes opens an empty tab (url "") instead of the target: navigate it over CDP."""
    for _ in range(10):
        targets = json.load(urllib.request.urlopen(f"http://{uilat.CDP}/json/list", timeout=20))
        pages = [t for t in targets if t["type"] == "page"]
        if any(t["url"].startswith("http") for t in pages):
            return
        if pages and pages[0]["url"] in ("", "about:blank") or pages and pages[0]["url"].startswith("chrome://newtab"):
            ws = WebSocket(uilat.CDP, "/devtools/page/" + pages[0]["id"])
            ws.send(json.dumps({"id": 1, "method": "Page.navigate", "params": {"url": url}}))
            ws.recv()
            ws.sock.close()
            print(f"  empty tab, navigated to {url}", flush=True)
            time.sleep(5)
            return
        time.sleep(2)


def measure(br, tag, site, rnd):
    url, gap, keys = SITES[site]
    ensure_page(url)
    if not wait_ready(site):
        print(f"{tag} {site} #{rnd}: page not ready", flush=True)
    time.sleep(8)   # late scripts, ads, thumbnails
    # Google's EU/UK consent page: the least-sharing choice. adblock_run.reject_consent has no redirect wait.
    if page_eval("""(() => { const b = [...document.querySelectorAll("button")]
        .find(e => /reject all/i.test(e.textContent)); if (b) { b.click(); return true; } return false; })()"""):
        time.sleep(4)
    info = json.loads(page_eval(PAGE_INFO))
    page_eval(OBSERVE)
    br.sync_children()
    br.histograms(True)
    before = snapshot()
    t = time.time()
    kind, count = inputs(keys)
    if kind in ("hover", "cdpwheel"):
        cdp_pointer(keys, gap)
    else:
        dev = f"/media/developer/temp/evkeys {WHEEL_DEV}" if kind == "wheel" else uilat.EVKEYS
        bench.tv(f"{dev} {gap} {' '.join(map(str, keys))}", timeout=120)
    seconds = time.time() - t
    after = snapshot()
    # A busy main thread still holds keys after the last press (Daily Mail): wait until every key reached the page,
    # so their Event Timing entries exist. drain_s is how long that took; Runtime.evaluate itself waits for the thread.
    # Chrome coalesces wheel events (27 of 30 notches reached Wikipedia, the scroll was complete), so for the wheel the
    # wait ends when the count stops growing for 2 s.
    t, last, still = time.time(), -1, 0
    while time.time() - t < 30 and kind != "hover":
        try:
            n = page_eval(f"window.__il.{'got' if kind == 'key' else 'n.wheel'}")
            if kind == "key" and n >= count:
                break
            still = still + 1 if n == last else 0
            last = n
            if kind in ("wheel", "cdpwheel") and still >= 2:
                break
        except Exception:   # an evaluate timed out on the blocked thread
            pass
        time.sleep(1)
    drain = time.time() - t
    time.sleep(2)
    res = json.loads(page_eval(COLLECT))
    info["scrollY_after"] = page_eval("Math.round(scrollY)")
    info["focused_after"] = page_eval("(e => [e.tagName, e.id, (e.getAttribute('aria-label') || e.textContent || '')"
                                      ".trim().slice(0, 40)].join(' | '))(document.activeElement)")
    br.sync_children()
    hs = br.histograms(True)
    br.ws.sock.close()
    rec = {"tag": tag, "site": site, "round": rnd, "keys": count, "kind": kind, "gap": gap, "n": res["n"],
           "other": res["other"], "raf": res.get("raf", []), "wheel_t": res.get("wheelT", []), "seconds": round(seconds, 1), "drain_s": round(drain, 1),
           "page": info, "cpu": cpu_delta(before, after), "events": res["ev"], "prevented": res["prevented"], "got": res["got"],
           "loaf": res["loaf"],
           "hist": {k: uilat.stats(h) for k, h in sorted(hs.items()) if h["count"] and (
               k.startswith("EventLatency.") or "Scroll" in k or "Smoothness" in k)}}
    print("INPUTLAT " + json.dumps(rec), flush=True)
    summary(rec)


def summary(rec):
    ev = rec["events"]

    def mean(xs):
        return sum(xs) / len(xs) if xs else 0
    delay = mean([e[1] - e[0] for e in ev])
    handler = mean([e[2] - e[1] for e in ev])
    total = mean([e[3] for e in ev])
    c = rec["cpu"]
    busy = sum(c["ms_by_type"].values())
    print(f"  {rec['tag']} {rec['site']}: keydown >=16ms {len(ev)}/{rec['keys']}, mean {total:.0f} ms (input delay "
          f"{delay:.0f}, handlers {handler:.0f}, to paint {total - delay - handler:.0f}); prevented "
          f"{sum(rec['prevented'])}/{len(rec['prevented'])}; LoAF {len(rec['loaf'])} sum "
          f"{sum(l['d'] for l in rec['loaf']):.0f} ms; chrome CPU {busy / rec['keys']:.0f} ms/key, TV "
          f"{c['ms_all_tv_cpus'] / rec['keys']:.0f} ms/key; swap in/out {c['swap_pages_in']}/{c['swap_pages_out']}",
          flush=True)
    print(f"    {rec.get('kind', 'key')}: page got {rec.get('n')}, scrollY {rec['page'].get('scrollY')} -> "
          f"{rec['page'].get('scrollY_after')}, focus after {rec['page'].get('focused_after')}", flush=True)
    print(f"    threads {c['top_threads']}", flush=True)
    print(f"    other processes {c['top_other_procs']}", flush=True)
    for k, v in rec["hist"].items():
        if "Smoothness" in k or k.endswith(("TotalLatency", "RendererMainProcessing", "RendererCompositorQueueingDelay",
                       "SubmitCompositorFrameToPresentationCompositorFrame", "EndActivateToSubmitCompositorFrame")):
            print(f"    {k} {v}", flush=True)


def hmean(rs, name):
    """Mean of a histogram over runs, weighted by count; None when no run recorded it."""
    n = tot = 0
    for r in rs:
        h = r["hist"].get(name)
        if h:
            c = int(h.split("n=")[1].split()[0])
            n, tot = n + c, tot + c * float(h.split("mean=")[1].split()[0])
    return tot / n if n else None


def raf_stats(rs):
    """From the rAF log, while the page scrolled (a frame whose scrollY differs from the previous one, plus the frames
    between two such): mean frame interval and the share of intervals over 25 ms (a missed 60 Hz frame and more)."""
    gaps = []
    for r in rs:
        f = r.get("raf") or []
        moving = [i for i in range(1, len(f)) if f[i][1] != f[i - 1][1]]
        if len(moving) < 2:
            continue
        gaps += [f[i][0] - f[i - 1][0] for i in range(moving[0], moving[-1] + 1)]
    if not gaps:
        return None, None
    return sum(gaps) / len(gaps), 100 * sum(g > 25 for g in gaps) / len(gaps)


def wheel_to_frame(rs):
    """Per wheel event: from its timeStamp (when the OS event was made, page clock) to the first rAF frame whose
    scrollY differs from the scrollY at the event. Main-thread view, presentation not included: a bound that does not
    depend on the EventLatency presentation timestamps."""
    out = []
    for r in rs:
        f = r.get("raf") or []
        for t, y in r.get("wheel_t") or []:
            nxt = next((ft for ft, fy in f if ft >= t and fy != y), None)
            if nxt is not None:
                out.append(nxt - t)
    return (sum(out) / len(out), sorted(out)[len(out) // 2]) if out else (None, None)


def show_pointer(groups):
    """Wheel: latency of a notch to the screen (EventLatency, us -> ms), the share of scroll frames that came late,
    which thread scrolled (Renderer4.ScrollingThread: 0 compositor, 1 main, 2 compositor blocked on main), CPU per
    notch. Hover: pointer move to the screen, mouseover handler entries."""
    def f(x, fmt="6.0f"):
        return format(x, fmt) if x is not None else "     -"
    for kind in ("wheel", "hover"):
        rows = {k: v for k, v in groups.items() if v[0]["kind"] == kind}
        if not rows:
            continue
        print(f"\n{kind}: site tag runs got  " + ("scroll-px  notch-ms  first-ms  late-frames%  thread  raf-ms  raf>25ms%  wheel->frame mean/p50"
              if kind == "wheel" else "move-ms  over>=16ms  over-ms") +
              "  LoAF/in  main/in  viz/in  chrome/in  surface-mgr/in  TV/in  (ms)")
        for (site, tag), rs in sorted(rows.items()):
            n = sum(r["keys"] for r in rs)
            got = sum(r["n"]["wheel" if kind == "wheel" else "mousemove"] for r in rs)
            th = lambda name: sum(v for r in rs for k, v in r["cpu"]["top_threads"].items() if k == name) / n
            sm = sum(v for r in rs for k, v in r["cpu"]["top_other_procs"].items()
                     if k.startswith("surface-manager")) / n
            head = f"{site:13} {tag:22} {len(rs):2} {got:4}/{n:<4}"
            if kind == "wheel":
                px = sum((r["page"].get("scrollY_after") or 0) - (r["page"].get("scrollY") or 0) for r in rs) / len(rs)
                mid = (f"{px:8.0f}  {f(hmean(rs, 'EventLatency.GestureScrollUpdate.Wheel.TotalLatency2') and hmean(rs, 'EventLatency.GestureScrollUpdate.Wheel.TotalLatency2') / 1000)}"
                       f"  {f(hmean(rs, 'EventLatency.FirstGestureScrollUpdate.Wheel.TotalLatency2') and hmean(rs, 'EventLatency.FirstGestureScrollUpdate.Wheel.TotalLatency2') / 1000)}"
                       f"  {f(hmean(rs, 'Event.ScrollJank.DelayedFramesPercentage4.PerScroll'), '11.0f')}"
                       f"  {f(hmean(rs, 'Renderer4.ScrollingThread.Wheel'), '6.1f')}"
                       f"  {f(raf_stats(rs)[0], '6.1f')}  {f(raf_stats(rs)[1], '9.0f')}"
                       f"  {f(wheel_to_frame(rs)[0], '9.0f')}/{f(wheel_to_frame(rs)[1], '.0f')}")
            else:
                over = [e for r in rs for e in r["other"] if e[0] in ("mouseover", "pointerover")]
                mm = hmean(rs, "EventLatency.MouseMoved.TotalLatency")
                mid = (f"{f(mm and mm / 1000)}  {len(over):9}  "
                       f"{f(sum(e[4] for e in over) / len(over) if over else None)}")
            print(f"{head}  {mid}  {sum(l['d'] for r in rs for l in r['loaf']) / n:7.0f}  {th('renderer/chrome'):7.0f}"
                  f"  {th('browser/VizCompositorTh'):6.0f}  {sum(sum(r['cpu']['ms_by_type'].values()) for r in rs) / n:9.0f}"
                  f"  {sm:14.0f}  {sum(r['cpu']['ms_all_tv_cpus'] for r in rs) / n:5.0f}")
    print()


def show(paths):
    """Means per site and tag over every INPUTLAT record in the files: keydown duration (only entries >= 16 ms count,
    so the share of keys that reached 16 ms is printed too), its input delay, EventLatency mean, LoAF time, CPU."""
    recs = [json.loads(line[9:]) for p in paths for line in open(p) if line.startswith("INPUTLAT ")]
    # got: keys that reached the page (capture listener, records from 2026-11-20 on). A run where fewer than half
    # arrived even after the drain wait measured nothing (window without focus, page frozen): dropped and counted.
    groups, dropped = {}, {}
    for r in recs:
        # Wheel: Chrome coalesces wheel events while the main thread is busy (reddit: 10-17 events for 30 notches with
        # the whole scroll done), so a wheel run counts when the page scrolled at all.
        got = {"key": r.get("got", r["keys"]), "wheel": r.get("n", {}).get("scroll", 0) and r["keys"], "cdpwheel": r.get("n", {}).get("scroll", 0) and r["keys"],
               "hover": r.get("n", {}).get("mousemove", 0)}[r.get("kind", "key")]
        if got * 2 < r["keys"] and r.get("kind") != "hover" or got == 0:
            dropped[(r["site"], r["tag"])] = dropped.get((r["site"], r["tag"]), 0) + 1
            continue
        groups.setdefault((r["site"], r["tag"]), []).append(r)

    def mean(xs):
        return sum(xs) / len(xs) if xs else 0
    print("site   tag                          runs  keys>=16ms  dur ms  inputdelay  EventLat ms  LoAF ms/key  "
          "renderer-main ms/key  chrome ms/key  TV ms/key")
    show_pointer({k: v for k, v in groups.items() if v[0].get("kind") in ("wheel", "hover")})
    groups = {k: v for k, v in groups.items() if v[0].get("kind", "key") == "key"}
    for (site, tag), rs in sorted(groups.items()):
        ev = [e for r in rs for e in r["events"]]
        keys = sum(r["keys"] for r in rs)
        el = [float(r["hist"]["EventLatency.KeyPressed.TotalLatency"].split("mean=")[1].split()[0]) / 1000
              for r in rs if "EventLatency.KeyPressed.TotalLatency" in r["hist"]]
        main = sum(v for r in rs for k, v in r["cpu"]["top_threads"].items() if k == "renderer/chrome")
        print(f"{site:6} {tag:30} {len(rs):4}  {len(ev):4}/{keys:<4}  {mean([e[3] for e in ev]):6.0f}  "
              f"{mean([e[1] - e[0] for e in ev]):10.0f}  {mean(el):11.0f}  "
              f"{sum(l['d'] for r in rs for l in r['loaf']) / keys:11.0f}  {main / keys:20.0f}  "
              f"{sum(sum(r['cpu']['ms_by_type'].values()) for r in rs) / keys:13.0f}  "
              f"{sum(r['cpu']['ms_all_tv_cpus'] for r in rs) / keys:9.0f}")
    for (site, tag), n in sorted(dropped.items()):
        print(f"dropped: {site} {tag} {n} run(s), keys did not reach the page within 30 s")


def main():
    cmd = sys.argv[1]
    if cmd == "run":
        tags, rounds, sites = sys.argv[2].split(","), int(sys.argv[3]), sys.argv[4].split(",")
        stamp = int(time.time()) % 100000
        print(f"run.sh before the series: {runsh_restore()}", flush=True)
        for r in range(rounds):
            for site in sites:
                for tag in tags:
                    try:
                        run(tag, site, f"{stamp}-{r}")
                    except Exception as e:   # a crashed renderer or a page that navigated away: note it, go on
                        print(f"FAILED {tag} {site} {stamp}-{r}: {type(e).__name__} {e}", flush=True)
                        traceback.print_exc(limit=4, file=sys.stdout)
    elif cmd == "show":
        show(sys.argv[2:])
    elif cmd == "settings":
        tag, action = sys.argv[2], sys.argv[3]
        uilat.start(tag, "about:blank").ws.sock.close()
        if action == "get":
            print(settings_get())
        elif action == "set":
            print(settings_put(json.dumps({**json.loads(settings_get()), **json.loads(sys.argv[4])})))
        elif action == "restore":
            print(settings_put(open(sys.argv[4]).read().strip()))
        uilat.fire(uilat.close_all())


if __name__ == "__main__":
    main()
