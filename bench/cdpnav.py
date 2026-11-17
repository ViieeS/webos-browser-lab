#!/usr/bin/env python3
"""navtime.py for Chromium DevTools (CDP), e.g. chromium120 content_shell on :9224: navigates the
first page target to <url>, waits, then reads the page's own Navigation/Paint Timing, the same
expression navtime.py uses for WebKit.
usage: cdpnav.py <url> [wait s, default 35] [tv ip:port, default $TV_HOST:9224] [selector to count]
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inspector import WebSocket  # noqa: E402

url = sys.argv[1]
wait = float(sys.argv[2]) if len(sys.argv) > 2 else 35
hostport = sys.argv[3] if len(sys.argv) > 3 else os.environ["TV_HOST"] + ":9224"
count = sys.argv[4] if len(sys.argv) > 4 else "ytd-rich-item-renderer"


def page_socket():
    targets = json.load(urllib.request.urlopen(f"http://{hostport}/json/list", timeout=20))
    page = next(t for t in targets if t["type"] == "page")
    return WebSocket(hostport, "/devtools/page/" + page["id"])


def call(ws, method, params, timeout=20):
    ws.send(json.dumps({"id": 1, "method": method, "params": params}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = json.loads(ws.recv())
        if msg.get("id") == 1:
            return msg
    raise TimeoutError(method)


ws = page_socket()
call(ws, "Page.navigate", {"url": url})
ws.sock.close()
time.sleep(wait)
expr = ("JSON.stringify({nav: (n => n ? {dcl: Math.round(n.domContentLoadedEventEnd), load: Math.round(n.loadEventEnd)} : null)"
        "(performance.getEntriesByType('navigation')[0]),"
        " fcp: (performance.getEntriesByType('paint').find(p => p.name === 'first-contentful-paint') || {}).startTime | 0,"
        f" count: document.querySelectorAll({json.dumps(count)}).length, url: location.href.slice(0, 60)}})")
ws = page_socket()
msg = call(ws, "Runtime.evaluate", {"expression": expr, "returnByValue": True})
print("NAVTIME", msg.get("result", {}).get("result", {}).get("value", msg))
