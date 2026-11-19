#!/usr/bin/env python3
"""YouTube 4K60 in a cr151 build, measured without eyes: does 2160p60 play at 1x without drops?
A fresh profile (the owner's TV Tools settings stay untouched) with TV Tools' maxRes raised to 2160 (its "Auto" stops
at 1080p60), the player asked for hd2160. Every 3 s: the player's stats for nerds (resolution and fps, dropped
frames, buffer health), currentTime against the wall clock, the video element's decoded/dropped counts, and frames
seen by requestVideoFrameCallback. A CPU snapshot (threads_cr151.sh) halfway.
usage: yt4k.py <tag> <video id> [seconds, default 90]
Needs TV_HOST, tcprelay <TV LAN ip> 9226 -> 9225, lighttpd (bench/lighttpd.conf).
"""
import json
import sys
import time

import adblock_run as ab
import bench
import uilat

uilat.APPS["cr151b"] = "com.viiees.cr151b"

RVFC = """(() => { const v = document.querySelector("video"); if (!v || v.__rvfc) return !!v;
  v.__rvfc = {n: 0, gaps: []}; let last = 0;
  const cb = (now, meta) => { const s = v.__rvfc; s.n++; if (last) s.gaps.push(now - last); last = now;
    if (s.gaps.length > 600) s.gaps.shift(); v.requestVideoFrameCallback(cb); };
  v.requestVideoFrameCallback(cb); return true; })()"""
SAMPLE = """(() => { const p = document.querySelector("#movie_player"), v = document.querySelector("video");
  if (!v) return null; let s = {}; try { s = p.getStatsForNerds(); } catch (e) {}
  const q = v.getVideoPlaybackQuality(), r = v.__rvfc || {n: 0, gaps: []}, g = r.gaps.slice().sort((a, b) => a - b);
  const pct = x => g.length ? +g[Math.min(g.length - 1, Math.floor(g.length * x))].toFixed(1) : null;
  const out = {ad: p && p.classList.contains("ad-showing"), t: +v.currentTime.toFixed(2), paused: v.paused,
    res: s.resolution, codecs: s.codecs, yt_dropped: s.dropped_frames, health: s.buffer_health_seconds,
    q: p && p.getPlaybackQuality ? p.getPlaybackQuality() : null, frames: q.totalVideoFrames,
    dropped: q.droppedVideoFrames, rvfc: r.n, gap_p50: pct(0.5), gap_p95: pct(0.95), gap_max: g.length ? +g[g.length - 1].toFixed(1) : null};
  r.gaps.length = 0; return out; })()"""


def tvtools_4k():
    """Raise TV Tools' maxRes to 2160 in this (fresh) profile, through its service worker."""
    sw = next(t for t in ab.targets() if t["type"] == "service_worker" and "bg.js" in t["url"])
    return ab.evaluate(sw["id"], """chrome.storage.local.get("settings").then(r => {
        const s = Object.assign({}, r.settings || {}, {maxRes: 2160});
        return chrome.storage.local.set({settings: s}).then(() => s); })""", await_promise=True)


def main():
    tag, vid = sys.argv[1], sys.argv[2]
    seconds = int(sys.argv[3]) if len(sys.argv) > 3 else 90
    uilat.VARIANTS["fresh4k"] = f"--user-data-dir=/tmp/{uilat.APPS[tag]}/fresh4k{int(time.time())}"
    br = uilat.start(f"{tag}+fresh4k", page=ab.START_PAGE)
    time.sleep(6)
    print(f"{tag} {vid} tvtools settings: {json.dumps(tvtools_4k())}", flush=True)
    ab.open_url(f"https://www.youtube.com/watch?v={vid}")
    time.sleep(8)
    start = time.time()
    while time.time() - start < seconds:
        time.sleep(3)
        try:
            if ab.reject_consent():
                print(f"{tag} {vid} +{time.time() - start:.0f}s consent: Reject all", flush=True)
            ab.page_eval("""(() => { const p = document.querySelector("#movie_player"), v = document.querySelector("video");
                if (p && p.setPlaybackQualityRange) p.setPlaybackQualityRange("hd2160", "hd2160");
                if (v && v.paused && !(p && p.classList.contains("ad-showing"))) v.play().catch(() => {}); })()""",
                         user_gesture=True)
            ab.page_eval(RVFC)
            if abs(time.time() - start - seconds / 2) < 1.6:
                uilat.fire("sh /media/developer/temp/threads_cr151.sh snap A; sleep 8; "
                           "sh /media/developer/temp/threads_cr151.sh snap B")
                cpu = bench.tv("sh /media/developer/temp/threads_cr151.sh diff A B | head -n 8 | tr '\\n' ';'")
                print(f"{tag} {vid} cpu 8s: {' '.join(cpu.split())}", flush=True)
            s = ab.page_eval(SAMPLE)
        except Exception as e:
            s = {"error": str(e)[:80]}
        print(f"{tag} {vid} +{time.time() - start:.1f}s {json.dumps(s, separators=(',', ':'))}", flush=True)
    br.ws.sock.close()
    uilat.fire(uilat.close_all())


if __name__ == "__main__":
    main()
