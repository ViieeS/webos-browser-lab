#!/usr/bin/env python3
"""A/B of the runtime trims in cr151/TRIM_CANDIDATES.md on the installed Chromium TV (com.viiees.chromiumtv).
Every run is a fresh launch with the variant's browser.flags; variants alternate inside each round.
usage: trim_run.py <rounds> <case>...        cases: load-wiki speedometer (harness beacons), heavy (live pages, memory),
                                             omnipre (omnibox typing: preloading memory and navigation)
       trim_run.py variations <variant>...   active field trials and features of a variant (chrome://version)
TRIM_VARIANTS=base,noft (comma list) picks variants; default: all of VARIANTS.
Needs TV_HOST, tcprelay <TV LAN ip> 9226 -> 9225, lighttpd (bench/lighttpd.conf), keepawake.sh.
"""
import json
import os
import sys
import time
import urllib.parse

import adblock_run
import bench
import uilat

APP_TAG = "chromiumtv"
RUNSH = "/media/developer/apps/usr/palm/applications/com.viiees.chromiumtv/bin/run.sh"
# run.sh's own --disable-features list (installed package, WebGPU default included). A second --disable-features in
# browser.flags replaces it, because the last switch wins, so a variant that adds features repeats it.
RUNSH_OFF = ("Translate,OptimizationHints,MediaRouter,BackForwardCache,Vulkan,ContextualTasks,ContextualTasksContext,"
             "ContextualTasksSidePanel,PreloadTopChromeWebUI,SpareRendererForSitePerProcess,SpareRenderer,"
             "OptimizationGuideModelDownloading,IsolateOrigins,site-per-process,WebUIToolbar,WebUIToolbarWebView,"
             "WebUIToolbarInternalWebView,WebUIReloadButton,WebUILocationBar,AudioServiceOutOfProcess,WebUIOmniboxPopup,"
             "WebUIOmniboxAimPopup,WebUIOmniboxFullPopup,DisableLoadExtensionCommandLineSwitch,HardwareMediaKeyHandling,"
             "OmniboxDynamicMaxAutocomplete,OmniboxRichAutocompletion,MlUrlScoring,UrlScoringModel,MlUrlScoreCaching,"
             "AimEnabled,AllowAiModeMatches,OmniboxMiaZPS,PreconnectNonSearchOmniboxSuggestions,WebGPUService,"
             "WebGPUBlobCache")
PREDICT_OFF = "NavigationPredictor,SearchPrefetchServicePrefetching,PreconnectToSearch,LoadingPredictorUseOptimizationGuide"
NOFT = "--disable-field-trial-config"
NOPRED = f"--disable-features={RUNSH_OFF},{PREDICT_OFF}"
# LG's web app manager values for TVs (TRIM_CANDIDATES.md row 4)
NEVA = ("--skia-resource-cache-limit-mb=40 --skia-font-cache-limit-mb=8 --decoded-image-working-set-budget-mb=96 "
        "--enable-aggressive-release-policy --tile-manager-low-mem-policy-bytes-limit-reduction-factor=2")
# rows 5, 12 and 13 together, measured on top of noft (on by default since this A/B)
MISC_OFF = ("BrowsingTopics,InterestGroupStorage,Fledge,SharedStorageAPI,FencedFrames,PrivateAggregationApi,"
            "ConversionMeasurement,Journeys,PageContentAnnotations,AutofillServerCommunication")
NOFTMISC = f"{NOFT} --disable-features={RUNSH_OFF},{MISC_OFF} --disable-domain-reliability"
# Which field trial makes base faster than noft: noft plus a chosen set of studies from the testing config, forced the
# way chrome://version/?show-variations-cmd prints them. fieldtrial_linux.json: the first experiment of every Linux
# study in M151's testing/variations/fieldtrial_testing_config.json, which is the one the build applies.
STUDIES = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fieldtrial_linux.json")))
RUNSH_ON = "NetworkServiceInProcess2,OmniboxUIExperimentMaxAutocompleteMatches:UIMaxAutocompleteMatches/5"
OMNI_TRIAL = "OmniboxBundledExperimentV1/TV"
OMNI_PARAMS = ("OmniboxBundledExperimentV1.TV:DisableProviders/201221632/SuggestPollingDelayMs/400/"
               "MeasureSuggestPollingDelayFromLastKeystroke/true")


def plain(s):   # names that survive the switch syntax as they are (the WebRTC studies pack params into group names)
    return not any(c in s for c in " ,/:<*")


def with_studies(names):
    on, off, trials, params = [RUNSH_ON], [RUNSH_OFF], [OMNI_TRIAL], [OMNI_PARAMS]
    for n in names:
        s = STUDIES[n]
        trials.append(f"{n}/{s['name']}")
        on += [f"{f}<{n}" for f in s.get("enable_features", [])]
        off += [f"{f}<{n}" for f in s.get("disable_features", [])]
        if s.get("params"):
            q = lambda v: urllib.parse.quote(str(v), safe="")
            params.append(f"{n}.{s['name']}:" + "/".join(f"{q(k)}/{q(v)}" for k, v in s["params"].items()))
    return (f"{NOFT} --enable-features={','.join(on)} --disable-features={','.join(off)} "
            f"--force-fieldtrials={'/'.join(trials)}/ --force-fieldtrial-params={','.join(params)}")


PLAIN = sorted(n for n, s in STUDIES.items() if plain(n) and plain(s["name"]))
GROUPS = {"v8": [n for n in PLAIN if n.startswith("V8") or n in ("MigrateAutomaticJsOptimizer", "PartialPageZeroing")],
          "pa": [n for n in PLAIN if n.startswith(("PartitionAlloc", "BrowserThreadPool", "ThreadPool"))],
          "h1": PLAIN[:len(PLAIN) // 2], "h2": PLAIN[len(PLAIN) // 2:],
          # the v8 group split: compiler and inline caches / heap and GC
          "v8jit": ["V8HomomorphicIC", "V8SparkplugPlus", "V8SideStepTransitions", "V8MaxValidPolymorphicMapCount",
                    "MigrateAutomaticJsOptimizer", "V8BytecodeVerification", "V8Turbolev"],
          "v8gc": ["V8PreconfigureOldGen", "V8SqrtAllocationLimits", "V8MemoryReducerDelay", "V8ManagedZoneMemory",
                   "V8CompactionOnRegularGCs", "V8MemoryPoolReleaseOnMallocFailures", "V8InputHandlingLongerWindow",
                   "V8SlowHistograms", "PartialPageZeroing"]}
assert sorted(GROUPS["v8jit"] + GROUPS["v8gc"]) == GROUPS["v8"]
GROUPS.update({"oldgen": ["V8PreconfigureOldGen"], "sqrt": ["V8SqrtAllocationLimits"],
               "gcrest": GROUPS["v8gc"][2:]})
# TRIM_STUDIES=V8Turbolev,V8SparkplugPlus: one more variant "noft+s" with just these
if os.environ.get("TRIM_STUDIES"):
    GROUPS["s"] = os.environ["TRIM_STUDIES"].split(",")

VARIANTS = {"base": "", "noft": NOFT, "nopred": NOPRED, "neva": NEVA, "all": f"{NOFT} {NOPRED} {NEVA}",
            "noftpred": f"{NOFT} {NOPRED}", "noftmisc": NOFTMISC,
            # the one study that made base faster than noft, as a plain V8 flag (its params are V8's defaults)
            "noftsqrt": f"{NOFT} --enable-features={RUNSH_ON},V8Flag_sqrt_allocation_limits",
            **{f"noft+{g}": with_studies(names) for g, names in GROUPS.items()}}
for name, flags in VARIANTS.items():
    if flags:
        uilat.VARIANTS[f"trim_{name}"] = flags
START_PAGE = f"{bench.HTTP}/pages/spatnav.html"
# live heavy pages (adblock_run's tab set), one tab each; memory is read after the last one settles
HEAVY = adblock_run.TAB_SITES[:5]
HEAVY_STEP_S = 40
HEAVY_SETTLE_S = 20


def chrome_gone():
    """A browser with heavy tabs takes longer than uilat.start's 4 s to exit after closeByAppId, and a launch then
    reuses it: the next variant ran on top of the last one's tabs. Wait up to 30 s, then kill what is left."""
    uilat.fire(uilat.close_all())
    for _ in range(15):
        if not bench.tv("pidof chrome").strip():
            return
        time.sleep(2)
    bench.tv("kill -9 $(pidof chrome) 2>/dev/null; sleep 2")


def launch(variant):
    chrome_gone()
    br = uilat.start(f"{APP_TAG}+trim_{variant}" if VARIANTS[variant] else APP_TAG, START_PAGE)
    for t in adblock_run.targets():   # first-run pages would take the foreground
        if t["type"] == "page" and not t["url"].startswith("http"):
            br.call("Target.closeTarget", {"targetId": t["id"]})
    br.call("Target.activateTarget", {"targetId": adblock_run.page_target()["id"]})
    return br


def meminfo():
    return " ".join(bench.tv(adblock_run.MEMINFO).split())


def heavy(variant, br, run):
    start = time.time()
    for n, url in enumerate(HEAVY, 1):
        try:
            br.call("Target.createTarget", {"url": url})
        except Exception as e:   # the browser did not answer: a result too (memory pressure), not a script error
            print(f"{variant} heavy #{run}: no answer at tab {n} ({type(e).__name__}) {meminfo()} {adblock_run.rss()}",
                  flush=True)
            return
        time.sleep(HEAVY_STEP_S)
    time.sleep(HEAVY_SETTLE_S)
    pages = [t for t in adblock_run.targets() if t["type"] == "page" and t["url"].startswith("http")]
    states = [adblock_run.tab_alive(t["id"]) for t in pages]
    print(f"{variant} heavy #{run}: s={round(time.time() - start)} pages={len(pages)} ok={states.count('ok')} "
          f"busy={states.count('busy')} {meminfo()} {adblock_run.rss()}", flush=True)


ENTER = 28
# activationStart > 0: the page was prerendered and only shown on Enter. Load is counted from activation, as
# web-vitals does, so a prerendered page reads near 0.
NAV = ("JSON.stringify((e => ({url: location.href.slice(0, 50), act: Math.round(e.activationStart || 0), "
       "load: Math.round(e.loadEventEnd - (e.activationStart || 0))}))(performance.getEntriesByType('navigation')[0]))")


def omnipre(variant, br, run):
    """Types "wikipedia" in the omnibox, waits with the popup open (prefetch and prerender start here), reads memory,
    then Enter. Prints the preloading histograms and the navigation timing of the page Enter opened."""
    br.sync_children()
    br.histograms(True)   # reset the delta
    uilat.press([str(uilat.F6), "w600", *map(str, uilat.WIKIPEDIA), "w5000"])
    typed = f"{meminfo()} {adblock_run.rss()}"
    uilat.press([str(ENTER), "w8000"])
    br.sync_children()
    hist = uilat.show(br.histograms(True), ("Prerender.", "Preloading.", "Omnibox.SearchPrefetch", "Navigation.Prefetch"))
    print(f"{variant} omnipre #{run}: nav={uilat.page_eval(NAV)} typed: {typed} hist: {hist}", flush=True)


def variations(variant):
    br = launch(variant)
    tid = br.call("Target.createTarget", {"url": "chrome://version/?show-variations-cmd", "background": True})["targetId"]
    time.sleep(4)
    text = adblock_run.evaluate(tid, "(document.querySelector('#variations-cmd') || {}).innerText || ''") or ""
    on = off = trials = 0
    for part in text.split():
        if part.startswith("--enable-features="):
            on = len(part.split("=", 1)[1].split(","))
        elif part.startswith("--disable-features="):
            off = len(part.split("=", 1)[1].split(","))
        elif part.startswith("--force-fieldtrials="):
            trials = part.count("/") // 2
    print(f"{variant} variations: trials={trials} enable_features={on} disable_features={off}", flush=True)
    br.ws.sock.close()
    uilat.fire(uilat.close_all())


def main():
    bench.tv("wget -q -O /dev/null http://127.0.0.1:8099/pages/spatnav.html || "
             "lighttpd -f /media/developer/bench/lighttpd.conf")
    uilat.fire("".join(f"luna-send -n 1 luna://com.webos.applicationManager/closeByAppId '{{\"id\":\"{a}\"}}' "
                       ">/dev/null; " for a in bench.BACKGROUND_APPS))
    # the variants repeat run.sh's feature list; stop if the installed run.sh no longer has it
    chrome_gone()
    got = bench.tv(f"grep -o -e '--disable-features=[^$]*' {RUNSH}")
    if RUNSH_OFF.rsplit(",WebGPUService", 1)[0] not in got:
        sys.exit(f"installed run.sh has another --disable-features list, update RUNSH_OFF: {got[:200]!r}")
    names = os.environ.get("TRIM_VARIANTS", ",".join(VARIANTS)).split(",")
    args = sys.argv[1:]
    if args[0] == "variations":
        for variant in args[1:] or names:
            variations(variant)
        return
    stamp = int(time.time()) % 100000
    for r in range(int(args[0])):
        for case in args[1:]:
            for variant in names:
                run = f"{stamp}-{r}"
                br = launch(variant)
                if case == "heavy":
                    heavy(variant, br, run)
                elif case == "omnipre":
                    omnipre(variant, br, run)
                else:
                    adblock_run.harness(variant, case, run)
                    print(f"{variant} {case} #{run} mem: {meminfo()}", flush=True)
                br.ws.sock.close()
                uilat.fire(uilat.close_all())


if __name__ == "__main__":
    main()
