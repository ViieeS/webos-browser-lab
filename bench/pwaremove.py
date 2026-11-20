#!/usr/bin/env python3
"""Removes an installed web app from Chromium TV the way chrome://apps does: the page's own "Remove from Chrome"
handler (app-item onUninstallItemClick_), which opens Chrome's native confirmation dialog.
usage: pwaremove.py <app name> [confirm keys...]
  The dialog takes keys (evkeys codes on event10; its focus starts on Uninstall, so 28 = Enter confirms);
  without keys the script stops at the open dialog.
Needs TV_HOST, tcprelay <TV LAN ip> 9226 -> 9225, /media/developer/temp/evkeys.
"""
import json
import sys
import time

import adblock_run as ab
import uilat

ITEMS = "[...document.querySelector('app-list').shadowRoot.querySelectorAll('app-item')]"
NAMES = f"{ITEMS}.map(i => i.appInfo.name)"


def main():
    name, keys = sys.argv[1], sys.argv[2:]
    br = uilat.start("chromiumtv", "chrome://apps")
    # the launch's "target" parameter does not open chrome:// pages, so the page comes in its own tab
    tid = br.call("Target.createTarget", {"url": "chrome://apps"})["targetId"]
    time.sleep(4)
    print("before:", json.dumps(ab.evaluate(tid, NAMES)))
    ok = ab.evaluate(tid, f"(() => {{ const i = {ITEMS}.find(i => i.appInfo.name === {json.dumps(name)});"
                          " if (!i) return false; i.onUninstallItemClick_(); return true; })()", user_gesture=True)
    if not ok:
        raise SystemExit(f"no app named {name}")
    time.sleep(3)
    if keys:
        uilat.press(keys)
        time.sleep(4)
        print("after:", json.dumps(ab.evaluate(tid, NAMES)))
    br.ws.sock.close()


if __name__ == "__main__":
    main()
