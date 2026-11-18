#!/usr/bin/env python3
"""YouTube playback diagnosis in WebOS-Chromium builds: why a video advances slowly.
Every 3 s for 60 s: ad shown, currentTime, paused, readyState, seconds buffered ahead, playbackRate, decoded and
dropped frames, page visibility, and the YouTube player's own "stats for nerds" (codec, resolution, buffer health).
At 30 s a CPU snapshot of the browser's threads (threads_cr151.sh). At the end the media lines of browser.log.
usage: ytplay.py <tag>[,<tag>...] <video id>...   tags: uilat.APPS (cr151 = 0.0.66, cr151own, cr151p) and cr151b
Needs TV_HOST, tcprelay <TV LAN ip> 9226 -> 9225, lighttpd (bench/lighttpd.conf), keepawake.sh running.
"""
import json
import sys
import time

import adblock_run as ab
import bench
import uilat

SAMPLE = """(() => { const p = document.querySelector("#movie_player"), v = document.querySelector("video");
  if (!v) return {video: false};
  let ahead = 0;
  for (let i = 0; i < v.buffered.length; i++)
    if (v.buffered.start(i) <= v.currentTime + 0.5) ahead = Math.max(ahead, v.buffered.end(i) - v.currentTime);
  const q = v.getVideoPlaybackQuality ? v.getVideoPlaybackQuality() : {};
  let s = {};
  try { s = p && p.getStatsForNerds ? p.getStatsForNerds() : {}; } catch (e) { s = {err: String(e)}; }
  return {ad: p ? p.classList.contains("ad-showing") : null, t: +v.currentTime.toFixed(1), paused: v.paused,
          rs: v.readyState, ns: v.networkState, ahead: +ahead.toFixed(1), rate: v.playbackRate,
          frames: q.totalVideoFrames, dropped: q.droppedVideoFrames, vis: document.visibilityState,
          focus: document.hasFocus(), w: v.videoWidth, h: v.videoHeight,
          yt: {codecs: s.codecs, res: s.resolution, health: s.buffer_health_seconds, kbps: s.bandwidth_kbps,
               dropped: s.dropped_frames, state: p && p.getPlayerState ? p.getPlayerState() : null}}; })()"""

# tag+autoplay: lets YouTube start the next media element itself. A CDP userGesture is transient, while a viewer's
# OK press on the remote leaves the page activated. Isolates the autoplay policy from decoding and network.
uilat.VARIANTS["autoplay"] = "--autoplay-policy=no-user-gesture-required"
uilat.APPS["cr151b"] = "com.viiees.cr151b"

LOG_GREP = "NDL|ndl|umedia|uMedia|MediaPlayer|lxvideodec|VideoDecoder|AudioRenderer|ERROR:.*media|stall|underflow"


def browser_log(app):
    return bench.tv(f"grep -E '{LOG_GREP}' /tmp/{app}/browser.log 2>/dev/null | tail -n 15 | cut -c1-220")


def run(tag, vid):
    app = uilat.APPS[tag.partition("+")[0]]
    br = uilat.start(tag, page=ab.START_PAGE)
    ab.open_url(f"https://www.youtube.com/watch?v={vid}")
    time.sleep(8)
    if ab.reject_consent():
        time.sleep(8)
    ab.page_eval("(v => { if (v) v.play().catch(() => {}); return !!v; })(document.querySelector('video'))",
                 user_gesture=True)
    start = time.time()
    for i in range(20):
        time.sleep(3)
        if i == 10:
            uilat.fire("sh /media/developer/temp/threads_cr151.sh snap A; sleep 8; "
                       "sh /media/developer/temp/threads_cr151.sh snap B")
            cpu = bench.tv("sh /media/developer/temp/threads_cr151.sh diff A B | head -n 8 | tr '\\n' ';'")
            print(f"{tag} {vid} cpu 8s: {cpu}", flush=True)
        try:
            # The consent lightbox comes 10-15 s after the page and pauses the player while open (a fresh profile
            # has no SOCS cookie). A viewer would answer it: take "Reject all" whenever it shows up.
            if ab.reject_consent():
                print(f"{tag} {vid} +{time.time() - start:.0f}s consent: Reject all", flush=True)
            s = ab.page_eval(SAMPLE)
        except Exception as e:
            s = {"error": str(e)[:60]}
        print(f"{tag} {vid} +{time.time() - start:.0f}s {json.dumps(s, separators=(',', ':'))}", flush=True)
    print(f"{tag} {vid} browser.log:\n{browser_log(app)}", flush=True)
    br.ws.sock.close()
    uilat.fire(uilat.close_all())


# Installed before YouTube's scripts: media events and play() rejections go to the console with a YTDBG prefix.
HOOK = """(() => { const t0 = performance.now(), log = (...a) => console.log("YTDBG", Math.round(performance.now() - t0), ...a);
  const play = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function () { const p = play.call(this);
    log("play()", this.currentTime.toFixed(1)); p.catch(e => log("play() rejected", e.name, e.message)); return p; };
  const pause = HTMLMediaElement.prototype.pause;   // a pause event without this log came from the browser itself
  HTMLMediaElement.prototype.pause = function () {
    log("pause()", this.currentTime.toFixed(1), (new Error().stack || "").split("\\n").slice(2, 16).map(s => s.trim()).join(" < "));
    return pause.call(this); };
  for (const ev of ["play", "playing", "pause", "waiting", "stalled", "error", "emptied", "ended", "loadedmetadata", "canplay", "seeking", "seeked"])
    document.addEventListener(ev, e => { const v = e.target; if (!(v instanceof HTMLMediaElement)) return;
      log("event", ev, v.currentTime.toFixed(1), "rs" + v.readyState, v.error ? "err" + v.error.code + ":" + v.error.message : ""); }, true);
})()"""


def events(tag, vid, seconds=70):
    """Console, exceptions and the HOOK's media log of one watch page, from navigation on."""
    br = uilat.start(tag, page=ab.START_PAGE)
    ws = ab.WebSocket(uilat.CDP, "/devtools/page/" + ab.page_target()["id"])
    for i, (m, p) in enumerate([("Runtime.enable", {}), ("Page.enable", {}),
                                ("Page.addScriptToEvaluateOnNewDocument", {"source": HOOK}),
                                ("Page.navigate", {"url": f"https://www.youtube.com/watch?v={vid}"})], 1):
        ws.send(json.dumps({"id": i, "method": m, "params": p}))
    ws.sock.settimeout(1)
    start, clicked = time.time(), False
    while time.time() - start < seconds:
        if not clicked and time.time() - start > 10:   # consent wall, then play as a click would
            clicked = True
            ws.send(json.dumps({"id": 90, "method": "Runtime.evaluate", "params": {"userGesture": True, "expression":
                """(() => { const b = [...document.querySelectorAll("button")].find(e => /reject all/i.test(e.textContent));
                   if (b) b.click(); const v = document.querySelector("video"); if (v) v.play().catch(() => {}); })()"""}}))
        try:
            m = json.loads(ws.recv())
        except OSError:
            continue
        t = f"{time.time() - start:5.1f}"
        if m.get("method") == "Runtime.consoleAPICalled":
            args = " ".join(str(a.get("value", a.get("description", "")))[:1500] for a in m["params"]["args"])
            if m["params"]["type"] in ("error", "warning") or args.startswith("YTDBG"):
                print(f"{tag} {t} console.{m['params']['type']}: {args[:1800]}", flush=True)
        elif m.get("method") == "Runtime.exceptionThrown":
            d = m["params"]["exceptionDetails"]
            print(f"{tag} {t} exception: {(d.get('exception', {}).get('description') or d.get('text', ''))[:300]}",
                  flush=True)
    ws.sock.close()
    br.ws.sock.close()
    uilat.fire(uilat.close_all())


def main():
    if sys.argv[1] == "events":   # ytplay.py events <tag>[,<tag>...] <video id>
        bench.tv("wget -q -O /dev/null http://127.0.0.1:8099/pages/spatnav.html || "
                 "lighttpd -f /media/developer/bench/lighttpd.conf")
        for tag in sys.argv[2].split(","):
            events(tag, sys.argv[3])
        return
    tags, ids = sys.argv[1].split(","), sys.argv[2:]
    bench.tv("wget -q -O /dev/null http://127.0.0.1:8099/pages/spatnav.html || "
             "lighttpd -f /media/developer/bench/lighttpd.conf")
    uilat.fire("".join(f"luna-send -n 1 luna://com.webos.applicationManager/closeByAppId '{{\"id\":\"{a}\"}}' "
                       ">/dev/null; " for a in bench.BACKGROUND_APPS))
    for vid in ids:
        for tag in tags:
            run(tag, vid)


if __name__ == "__main__":
    main()
