#!/usr/bin/env python3
"""Evaluates a JS expression in the first page target over CDP and prints the JSON value.
Runs as a user gesture, so play() with sound passes the autoplay policy.
usage: cdpeval.py '<expression>' [tv ip:port, default $TV_HOST:9224]
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inspector import WebSocket  # noqa: E402

expr = sys.argv[1]
hostport = sys.argv[2] if len(sys.argv) > 2 else os.environ["TV_HOST"] + ":9224"
targets = json.load(urllib.request.urlopen(f"http://{hostport}/json/list", timeout=20))
page = next(t for t in targets if t["type"] == "page")
ws = WebSocket(hostport, "/devtools/page/" + page["id"])
ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                    "params": {"expression": expr, "returnByValue": True, "awaitPromise": True,
                               "userGesture": True}}))
deadline = time.time() + 20
while time.time() < deadline:
    msg = json.loads(ws.recv())
    if msg.get("id") == 1:
        print(json.dumps(msg.get("result", msg)))
        break
ws.sock.close()
