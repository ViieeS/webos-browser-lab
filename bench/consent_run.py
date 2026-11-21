#!/usr/bin/env python3
"""Cookie-banner auto-reject in Chromium TV: what each candidate does on EU/UK sites, and what it costs.
Variants (all with TV Tools and uBO Lite in complete mode, as shipped):
  base       uBO Lite as shipped (its "Cookie Notices" list is off)
  ubolck     uBO Lite with its "EasyList/uBO – Cookie Notices" ruleset on
  ac         base + DuckDuckGo autoconsent (MV3 add-on from the npm package, built by consent_prep.sh)
  lean       base + autoconsent, lean build (consent_prep.sh says what changes)
  leannoh    lean without heuristic detection
  leanfr     lean with its content script in main frames and rule-matched subframes only
Every variant runs in a throwaway profile (--user-data-dir under /tmp/<app>, wiped before each launch), so the owner's
profile and its cookies are never touched; cookies and site storage are also cleared before every site.
uBO Lite runs from its own unpacked copy there, taken from the profile folder where Chrome unpacked the shipped CRX.
--disable-extensions-except keeps that CRX from installing itself a second time into the throwaway profile.
usage: consent_run.py effect <variant>...           per site: banner, the CMP's consent record, screenshot
       consent_run.py cost <rounds> <variant>...    load time and CPU on COST_SITES, cleared state every load
Needs TV_HOST, tcprelay <TV LAN ip> 9226 -> 9225, and consent_prep.sh's tars served at $AC_BASE (an http URL of that folder).
"""
import base64
import json
import os
import sys
import time

import adblock_run as ab
import bench
import uilat
from inspector import WebSocket

APP = uilat.APPS["chromiumtv"]
DATA = f"/media/developer/apps/usr/palm/applications/{APP}/data"
WORK = f"/tmp/{APP}/consent"
PROFILE = f"{WORK}/profile"
UBOL = f"{WORK}/ubol"
# Chromium TV ships uBO Lite as a CRX (package.sh); Chrome keeps the installed copy unpacked under the profile
UBOL_INSTALLED = f"{DATA}/profile/Default/Extensions/bbdfhfkcgpkhdkbgpnelelegbhpimcek"
AC = f"{WORK}/autoconsent"
# autoconsent builds from consent_prep.sh: the test add-on and the two lean ones
TARS = {"ac": "autoconsent.tar", "lean": "lean.tar", "leannoh": "lean-noh.tar", "leanfr": "lean-frames.tar"}
EXTS = {"base": [f"{DATA}/ext/tvtools", UBOL], "ubolck": [f"{DATA}/ext/tvtools", UBOL],
        **{v: [f"{DATA}/ext/tvtools", UBOL, AC] for v in TARS}}
for name, exts in EXTS.items():
    uilat.VARIANTS["c" + name] = (f"--user-data-dir={PROFILE} --load-extension={','.join(exts)}"
                                  f" --disable-extensions-except={','.join(exts)}")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "consent")
PROBE = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "consent_probe.js")).read()
START_PAGE = "about:blank"
SITES = [   # (name, url); the CMP each one serves is read from the run, not assumed
    ("guardian", "https://www.theguardian.com/uk"),
    ("independent", "https://www.independent.co.uk/"),
    ("booking", "https://www.booking.com/"),
    ("ikea", "https://www.ikea.com/gb/en/"),
    ("cookiebot", "https://www.cookiebot.com/en/"),
    ("20minutes", "https://www.20minutes.fr/"),
    ("usercentrics", "https://usercentrics.com/"),
    ("dm", "https://www.dm.de/"),
    ("mirror", "https://www.mirror.co.uk/"),
    ("bbc", "https://www.bbc.co.uk/"),
    ("amazon", "https://www.amazon.co.uk/"),
    ("youtube", "https://www.youtube.com/"),
    ("google", "https://www.google.com/search?q=weather"),
    ("reddit", "https://www.reddit.com/"),
]
COST_SITES = ["guardian", "booking", "20minutes"]
SETTLE_S = 20   # a CMP shows its banner seconds after load; YouTube's consent lightbox came 10-15 s after load
CPU = r"""for p in $(pidof chrome); do cut -d' ' -f14,15 /proc/$p/stat; done | awk '{s += $1 + $2} END {print s}'"""


def setup(variant):
    """Throwaway profile and the variant's extension copies under /tmp/<app>, owned by the app's user."""
    owner = bench.tv(f"stat -c %u:%g /tmp/{APP}").strip()
    cmd = (f"rm -rf {WORK} && mkdir -p {WORK} && cp -r \"$(ls -d {UBOL_INSTALLED}/*/ | tail -1)\" {UBOL}"
           f" && rm -rf {UBOL}/_metadata && [ -f {UBOL}/manifest.json ]")
    if variant in TARS:
        cmd += f" && mkdir -p {AC} && wget -q -O - {os.environ['AC_BASE']}/{TARS[variant]} | tar -x -C {AC}"
    if "ok" not in bench.tv(f"{cmd} && [ -f {AC}/manifest.json -o {variant!r} = 'base' -o {variant!r} = 'ubolck' ] && chown -R {owner} {WORK} && echo ok"):
        raise RuntimeError(f"{variant}: setup on the TV failed (add-on download?)")


def ubol_cookie_list(br, on):
    """Turns uBO Lite's Cookie Notices ruleset on or off from its dashboard, as its own Filter lists pane does."""
    url = f"chrome-extension://{ab.unpacked_id(UBOL)}/dashboard.html"
    tid = br.call("Target.createTarget", {"url": url, "background": True})["targetId"]
    time.sleep(3)
    got = ab.evaluate(tid, """(async () => {
        const d = await chrome.runtime.sendMessage({what: 'getOptionsPageData'});
        const set = new Set(d.enabledRulesets);
        %s set.add('annoyances-cookies'); %s
        await chrome.runtime.sendMessage({what: 'applyRulesets', enabledRulesets: [...set]});
        const e = await chrome.runtime.sendMessage({what: 'getOptionsPageData'});
        return JSON.stringify({mode: e.defaultFilteringMode, rulesets: e.enabledRulesets});
    })()""" % (("", "") if on else ("/*", "*/")), await_promise=True)
    br.call("Target.closeTarget", {"targetId": tid})
    return got


def launch(variant):
    br = uilat.start(f"chromiumtv+c{variant}", START_PAGE)
    print(f"{variant}: uBO Lite {ubol_cookie_list(br, variant == 'ubolck')}", flush=True)
    for t in ab.targets():   # first-run pages of the extensions would take the foreground
        if t["type"] == "page" and t["url"].startswith("chrome-extension://"):
            br.call("Target.closeTarget", {"targetId": t["id"]})
    return br


class Page:
    """CDP session on the one page tab."""

    def __init__(self):
        t = next(t for t in ab.targets() if t["type"] == "page")
        self.id = t["id"]
        self.ws = WebSocket(uilat.CDP, "/devtools/page/" + self.id)
        self.n = 0

    def call(self, method, params=None, timeout=60):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params or {}}))
        self.ws.sock.settimeout(timeout)
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def eval(self, expr):
        res = self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
        return res.get("result", {}).get("value")

    def origins(self):
        out = set()

        def walk(node):
            f = node["frame"]
            if f.get("securityOrigin", "").startswith("http"):
                out.add(f["securityOrigin"])
            for c in node.get("childFrames", []):
                walk(c)
        walk(self.call("Page.getFrameTree")["frameTree"])
        return out

    def clear(self, origins):
        self.call("Network.clearBrowserCookies")
        for o in origins:
            self.call("Storage.clearDataForOrigin", {"origin": o, "storageTypes": "all"})

    def goto(self, url):
        self.call("Page.navigate", {"url": url})


def socs(value):
    """Google's SOCS consent cookie: a base64url protobuf. Field 1 is the choice it records (calibrated by hand)."""
    raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    return raw[1] if raw[:1] == b"\x08" else None


def all_cookies(page):
    try:
        return page.call("Network.getAllCookies")["cookies"]
    except RuntimeError:   # removed from newer DevTools protocols in favour of Storage.getCookies
        return page.call("Storage.getCookies")["cookies"]


def cookies_of_interest(page):
    names = ("OptanonConsent", "OptanonAlertBoxClosed", "CookieConsent", "euconsent-v2", "didomi_token", "SOCS",
             "CONSENT", "uc_settings", "sp-cc", "ckns_policy", "consentUUID")
    got = {}
    for c in all_cookies(page):
        if c["name"] in names or "consent" in c["name"].lower():
            v = c["value"]
            got[f"{c['name']}@{c['domain']}"] = f"socs={socs(v)}" if c["name"] == "SOCS" else v[:80]
    return got


def autoconsent_reports(br):
    """The add-on's own per-frame reports (chrome.storage.session), read from one of its pages."""
    tid = br.call("Target.createTarget", {"url": f"chrome-extension://{ab.unpacked_id(AC)}/popup.html",
                                          "background": True})["targetId"]
    time.sleep(2)
    got = ab.evaluate(tid, """(async () => {
        const all = await chrome.storage.session.get(null);
        const out = [];
        for (const [k, v] of Object.entries(all)) {
            if (!k.startsWith('reports-')) continue;
            for (const r of Object.values(v)) {
                const s = r.state || {};
                if (s.lifecycle === 'nothingDetected' && !s.detectedCmps.length) continue;
                out.push({frame: r.url.slice(0, 60), main: r.mainFrame, life: s.lifecycle, cmps: s.detectedCmps,
                          popups: s.detectedPopups, clicks: s.clicks, selfTest: s.selfTest,
                          heuristic: (s.heuristicPatterns || []).length,
                          ms: s.endTime && s.startTime ? s.endTime - s.startTime : null});
            }
        }
        await chrome.storage.session.clear();
        return JSON.stringify(out);
    })()""", await_promise=True)
    br.call("Target.closeTarget", {"targetId": tid})
    return json.loads(got)


def effect(variant):
    os.makedirs(OUT, exist_ok=True)
    setup(variant)
    br = launch(variant)
    page = Page()
    page.call("Page.enable")
    page.call("Network.enable")
    seen = set()
    for name, url in SITES:
        page.clear(seen)
        page.goto(url)
        time.sleep(SETTLE_S)
        try:
            first = json.loads(page.eval(PROBE))
        except Exception as e:   # a page that never answers is a result too
            first = {"error": str(e)[:200]}
        shot = page.call("Page.captureScreenshot", {"format": "jpeg", "quality": 50})["data"]
        with open(os.path.join(OUT, f"{variant}_{name}.jpg"), "wb") as f:
            f.write(base64.b64decode(shot))
        seen |= page.origins()
        rec = {"variant": variant, "site": name, "probe": first, "cookies": cookies_of_interest(page)}
        if variant in TARS:
            rec["autoconsent"] = autoconsent_reports(br)
        # a choice the CMP stored keeps the banner away after a reload, a hidden-only banner is hidden again
        page.goto(url)
        time.sleep(12)
        try:
            again = json.loads(page.eval(PROBE))
            rec["reload"] = {"visible": again["visible"], "overlay": again["overlay"], "record": again["record"]}
        except Exception as e:
            rec["reload"] = {"error": str(e)[:200]}
        print(json.dumps(rec, ensure_ascii=False), flush=True)
    br.ws.sock.close()
    uilat.fire(uilat.close_all())


def cost(rounds, variant):
    """Per load: navigation timing, the page renderer's own task time, and the CPU of all chrome processes over
    a fixed window (the add-on's service worker runs outside the page's renderer)."""
    setup(variant)
    br = launch(variant)
    page = Page()
    page.call("Page.enable")
    page.call("Performance.enable")
    urls = dict(SITES)
    seen = set()
    for rnd in range(rounds):
        for name in COST_SITES:
            page.goto("about:blank")
            time.sleep(2)
            page.clear(seen)
            m0 = {m["name"]: m["value"] for m in page.call("Performance.getMetrics")["metrics"]}
            c0 = int(bench.tv(CPU).strip() or 0)
            page.goto(urls[name])
            time.sleep(SETTLE_S)
            c1 = int(bench.tv(CPU).strip() or 0)
            m1 = {m["name"]: m["value"] for m in page.call("Performance.getMetrics")["metrics"]}
            nav = page.eval("JSON.stringify((({domContentLoadedEventEnd: d, loadEventEnd: l}) => "
                            "({dcl: Math.round(d), load: Math.round(l)}))(performance.getEntriesByType('navigation')[0] || {}))")
            seen |= page.origins()
            print(json.dumps({"variant": variant, "site": name, "round": rnd, **json.loads(nav or "{}"),
                              "task_ms": round((m1["TaskDuration"] - m0["TaskDuration"]) * 1000),
                              "script_ms": round((m1["ScriptDuration"] - m0["ScriptDuration"]) * 1000),
                              "cpu_jiffies": c1 - c0}), flush=True)
    br.ws.sock.close()
    uilat.fire(uilat.close_all())


def main():
    if sys.argv[1] == "effect":
        for v in sys.argv[2:]:
            effect(v)
    elif sys.argv[1] == "cost":
        for v in sys.argv[3:]:
            cost(int(sys.argv[2]), v)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
