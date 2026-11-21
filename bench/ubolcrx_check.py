#!/usr/bin/env python3
"""Is uBO Lite installed from the external CRX, running, and blocking? Run after a launch with DevTools on.

Prints the extension service workers DevTools sees, then opens a known tracker URL in a new tab: uBO Lite's rules
turn it into chrome-error://chromewebdata/ with ERR_BLOCKED_BY_CLIENT. Needs TV_HOST, tcprelay 9226 -> 9225.
"""
import json
import os
import time
import urllib.request

from uilat import Browser

CDP = f"{os.environ['TV_HOST']}:9226"
TRACKER = "https://www.googletagmanager.com/gtm.js?id=GTM-TEST"

targets = json.load(urllib.request.urlopen(f"http://{CDP}/json/list", timeout=20))
for t in targets:
    if t["url"].startswith("chrome-extension://"):
        print("extension", t["type"], t["url"].split("/")[2])
br = Browser()
tid = br.call("Target.createTarget", {"url": TRACKER})["targetId"]
time.sleep(6)
for t in json.load(urllib.request.urlopen(f"http://{CDP}/json/list", timeout=20)):
    if t["id"] == tid:
        print("tracker tab:", t["url"][:60], "|", t["title"][:60])
br.call("Target.closeTarget", {"targetId": tid})
