#!/usr/bin/env python3
"""Print the TV's memory picture every 30 s while the browser runs: web process RSS, free memory,
swap in use and the last CRASH line, one line per sample (meant for a Monitor).
usage: tvmem.py <tv-ip> [samples, default 30] [interval s, default 30]
"""
import os
import subprocess
import sys
import time

TVTELNET = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bench", "tvtelnet.py")
LOG = "/var/palm/jail/com.viiees.browser/tmp/browser.log"
CMD = ("P=$(ps -eo rss,pid,comm | grep WPEWebProcess | sort -rn | head -1 | awk '{print $2}');"
       " echo $(grep -E 'VmSize|VmRSS' /proc/$P/status | tr -s ' \\t' ' ')"
       " avail=$(grep MemAvailable /proc/meminfo | tr -s ' ' | cut -d' ' -f2)"
       " swapfree=$(grep SwapFree /proc/meminfo | tr -s ' ' | cut -d' ' -f2)"
       f" crashes=$(grep -c CRASH {LOG})")

ip = sys.argv[1]
interval = int(sys.argv[3]) if len(sys.argv) > 3 else 30
for _ in range(int(sys.argv[2]) if len(sys.argv) > 2 else 30):
    out = subprocess.run(["python3", TVTELNET, ip, CMD], capture_output=True, text=True, timeout=60).stdout
    line = next((l for l in out.splitlines() if "avail=" in l), out.strip()[-120:])
    print(time.strftime("%H:%M:%S"), line, flush=True)
    time.sleep(interval)
