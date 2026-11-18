#!/usr/bin/env python3
"""Runs pages/video.html in our browser on the TV: capabilities once, then every clip (progressive and
MSE), each with the page's report (start, played seconds, dropped frames, stalls) and the CPU of the
web process threads during playback, whose names tell a hardware decoder from a software one.
usage: video_run.py [tag, default wpe]   (tag cr120: chromium120 content_shell via browser/cr120/run_tv.sh,
       tag cr120app: the same content_shell under dev app com.viiees.cr120, whose launcher plays video through NDL,
       tag cr151: WebOS-Chromium release app org.nativechromium.browser, also NDL through its launcher;
       tags cr151own, cr151p, cr151b: our builds com.viiees.cr151, .cr151p, .cr151b)
"""
import os
import re
import subprocess
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bench  # noqa: E402

TAG = sys.argv[1] if len(sys.argv) > 1 else "wpe"
CR120APP = TAG == "cr120app"
CR120 = TAG == "cr120" or CR120APP
CR151_APP = {"cr151": "org.nativechromium.browser", "cr151own": "com.viiees.cr151", "cr151p": "com.viiees.cr151p",
             "cr151b": "com.viiees.cr151b"}.get(TAG)
CR151 = CR151_APP is not None
T = ("/media/developer/temp/cr120/threads_cr120.sh" if CR120 else
     "sh /media/developer/temp/threads_cr151.sh" if CR151 else "/media/developer/temp/threads.sh")
CLIPS = [  # file, mode, MSE type
    ("h264aac-1080p30.mp4", "src", ""),  # with audio: uMediaServer stalls on video-only clips
    ("h264-1080p30.mp4", "src", ""), ("h264-1080p60.mp4", "src", ""), ("hevc-2160p30.mp4", "src", ""),
    ("vp9-1080p60.webm", "src", ""), ("vp9-2160p30.webm", "src", ""), ("av1-1080p30.mp4", "src", ""),
    ("h264-1080p30-frag.mp4", "mse", 'video/mp4; codecs="avc1.640028"'),
    ("vp9-1080p60.webm", "mse", 'video/webm; codecs="vp9"'), ("vp9-2160p30.webm", "mse", 'video/webm; codecs="vp9"'),
]
CLOSE = "".join(f"luna-send -n 1 luna://com.webos.applicationManager/closeByAppId '{{\"id\":\"{a}\"}}' >/dev/null; "
                for a in (bench.APP, *bench.BACKGROUND_APPS))
if CR120APP:
    CLOSE += "luna-send -n 1 luna://com.webos.applicationManager/closeByAppId '{\"id\":\"com.viiees.cr120\"}' >/dev/null; "
elif CR120:
    CLOSE += "sh /media/developer/temp/cr120/run_tv.sh stop; "
elif CR151:
    CLOSE += "luna-send -n 1 luna://com.webos.applicationManager/closeByAppId '{\"id\":\"%s\"}' >/dev/null; " % CR151_APP


def launch(query):
    url = f"{bench.HTTP}/pages/video.html?{query}"
    if CR120APP:
        payload = '{"id":"com.viiees.cr120","params":{"target":"%s","devtools":true}}' % url  # threads + CDP
        bench.tv(f"{CLOSE}sleep 3; luna-send -n 1 luna://com.webos.applicationManager/launch '{payload}' >/dev/null")
        return
    if CR120:
        bench.tv(f"{CLOSE}sleep 3; sh /media/developer/temp/cr120/run_tv.sh '{url}'")
        return
    if CR151:
        payload = '{"id":"%s","params":{"target":"%s"}}' % (CR151_APP, url)
        try:
            bench.tv(f"{CLOSE}sleep 3; luna-send -n 1 luna://com.webos.applicationManager/launch '{payload}' >/dev/null", timeout=20)
        except subprocess.TimeoutExpired:
            pass
        return
    payload = '{"id":"%s","params":{"url":"%s"}}' % (bench.APP, url)
    bench.tv(f"{CLOSE}sleep 3; pkill -9 -x browser; sleep 1")
    try:   # a session that launches an app may never return its end marker
        bench.tv(f"luna-send -n 1 luna://com.webos.applicationManager/launch '{payload}' >/dev/null", timeout=15)
    except subprocess.TimeoutExpired:
        pass


def beacon(run, case):
    out = bench.tv(f"grep 'beacon?tag={TAG}&run={run}&case={case}' /tmp/bench-access.log | tail -n 1")
    m = re.search(r"GET /beacon\?(\S+) HTTP", out)
    if not m:
        return "no report"
    kv = dict(urllib.parse.parse_qsl(m.group(1)))
    for k in ("tag", "run", "case"):
        kv.pop(k, None)
    return " ".join(f"{k}={v}" for k, v in kv.items())


stamp = int(time.time()) % 100000
bench.tv("wget -q -O /dev/null http://127.0.0.1:8099/pages/video.html || lighttpd -f /media/developer/bench/lighttpd.conf")
launch(f"caps=1&tag={TAG}&run={stamp}-caps")
time.sleep(12)
print("caps:", beacon(f"{stamp}-caps", "caps"), flush=True)
for i, (file, mode, mime) in enumerate(CLIPS):
    run = f"{stamp}-{i}"
    q = urllib.parse.urlencode({"file": file, "mode": mode, "mime": mime, "tag": TAG, "run": run})
    launch(q)
    time.sleep(8)    # page load, MSE appends, playback start
    bench.tv(f"{T} snap A")
    time.sleep(8)
    threads = bench.tv(f"{T} snap B; {T} diff A B | sort -rn | head -n 5 | tr -s ' ' | tr '\\n' ';'").strip()
    time.sleep(6)
    print(f"{file} {mode}: {beacon(run, 'play')} | cpu 8s: {threads}", flush=True)
bench.tv(CLOSE)
