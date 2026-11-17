#!/usr/bin/env python3
"""Wait until a file on the TV contains a pattern, then print the file. For jobs started detached on
the TV (tvtelnet stops at 180 s), run from the Mac in the background.
usage: tvwait.py <tv file> <pattern> [poll s, default 60] [give up after s, default 14400]
"""
import os
import subprocess
import sys
import time

TV = os.environ["TV_HOST"]
TVTELNET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tvtelnet.py")
path, pattern = sys.argv[1], sys.argv[2]
poll = int(sys.argv[3]) if len(sys.argv) > 3 else 60
deadline = time.time() + (int(sys.argv[4]) if len(sys.argv) > 4 else 14400)
while True:
    try:
        out = subprocess.run(["python3", TVTELNET, TV, f"cat {path}"],
                             capture_output=True, text=True, timeout=200).stdout
    except (subprocess.TimeoutExpired, OSError):
        out = ""   # TV briefly unreachable: keep waiting
    if pattern in out:
        print(out)
        break
    if time.time() > deadline:
        print(f"gave up waiting for {pattern!r}\n{out}")
        sys.exit(1)
    time.sleep(poll)
