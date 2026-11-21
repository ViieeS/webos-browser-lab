#!/usr/bin/env python3
"""Limits an autoconsent add-on's content script to the frames its rules can act in (autoconsent.sh, lean-frames).
The shipped manifest injects the 196 KB content script into every frame, ad frames included. Only these rules run in
a subframe: the Sourcepoint-frame CMP (its frame is recognised by path, on any host) and the JSON rules whose
runContext allows a subframe, each limited to a urlPattern. Heuristic detection runs in the main frame only.
So: one entry for main frames, one entry for subframes that match Sourcepoint's paths or those rules' hosts.
usage: consent_frames.py <add-on dir>      rewrites manifest.json; fails on a subframe rule it cannot map to a host
"""
import json
import re
import sys

# lib/cmps/sourcepoint-frame.ts, detectCmp(): the paths and hosts of its frames (the query is checked there again)
SOURCEPOINT = ["*://*/index.html?*", "*://*/privacy-manager/index.html?*", "*://*/ccpa_pm/index.html?*",
               "*://*/us_pm/index.html?*", "*://ccpa-notice.sp-prod.net/*", "*://ccpa-pm.sp-prod.net/*"]
# rule urlPatterns are anchored regexes such as ^https?://(www\.)?example\.com/ or ^https://([a-z]*\.)?web\.de/
HOST = re.compile(r"\^https\??://(?:\([^)]*\)[?*]?)?((?:[a-z0-9-]+\\\.)+[a-z]+)/")


def subframe_hosts(compact):
    hosts = set()
    for rule in compact["r"]:
        pattern, context = rule[3], rule[4]
        if context % 10 != 1:   # the ones digit is "run in subframes": 1 yes, 0 no, other unset (= no)
            continue
        if not pattern:
            print(f"autoconsent_frames: skipping subframe rule with no urlPattern: {rule[:3]}", file=sys.stderr)
            continue
        found = [h.replace("\\.", ".") for h in HOST.findall(pattern)]
        if not found:
            raise SystemExit(f"autoconsent_frames: cannot map urlPattern to a host: {pattern}")
        hosts.update(found)
    return sorted(hosts)


def main():
    root = sys.argv[1]
    compact = json.load(open(f"{root}/compact-rules.json"))
    hosts = subframe_hosts(compact)
    path = f"{root}/manifest.json"
    manifest = json.load(open(path))
    [entry] = manifest["content_scripts"]
    main_frames = {**entry, "all_frames": False}
    main_frames.pop("match_origin_as_fallback", None)
    sub_frames = {**entry, "matches": SOURCEPOINT + [f"*://*.{h}/*" for h in hosts], "all_frames": True}
    sub_frames.pop("match_origin_as_fallback", None)
    manifest["content_scripts"] = [main_frames, sub_frames]
    json.dump(manifest, open(path, "w"), indent=2)
    print(f"autoconsent_frames: main frames everywhere, subframes on {len(SOURCEPOINT)} Sourcepoint paths "
          f"and {len(hosts)} hosts")


if __name__ == "__main__":
    main()
