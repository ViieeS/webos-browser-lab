#!/usr/bin/env python3
"""Evaluate one JS expression in the inspected page and print the value (debugging the TV browsers).
usage: eval.py <expression> [tv ip:port, default $TV_HOST:9223]
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inspector import Inspector  # noqa: E402

insp = Inspector(sys.argv[2] if len(sys.argv) > 2 else os.environ["TV_HOST"] + ":9223")
ask = insp.send("Runtime.evaluate", {"expression": sys.argv[1], "returnByValue": True, "awaitPromise": True})
for msg in insp.messages(time.time() + 30):
    if msg.get("id") == ask:
        print(msg.get("result", msg.get("error")))
        break
