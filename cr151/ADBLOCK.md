# Adblocking in cr151: uBO Lite, uBlock Origin, adblock-rust (2026-11-18)

Question: which blocker gives the best blocking for the least speed and memory on the C1, and is a native engine
(Brave's adblock-rust) worth building in. The owner judges blockers on effectiveness and speed only.

## Result

| Variant | adblock-tester | YouTube ads (samples) | Speedometer 3 | Wikipedia load | News page DCL | RSS, all chrome |
|---|---|---|---|---|---|---|
| No blocker | tab crashes (see below) | 40 / 40 | 0.759 | 3.0 s | 48 s | 335 MB |
| uBO Lite, optimal | 91 / 100 | 0 / 40 | 0.756 | 3.2 s | 37 s | 455 MB |
| uBO Lite, complete | 96 / 100 | 0 / 40 | 0.728 | 3.6 s | 38 s | 470 MB |
| uBlock Origin (MV2) | 96 / 100 | 3 / 40 | 0.740 | 3.4 s | 40 s | 490 MB |

Medians. Speedometer: 2 rounds. Wikipedia and the news page: 3 rounds, interleaved over the variants. YouTube: two
videos, 20 samples 3 s apart each. RSS: on Wikipedia, every chrome process, TV Tools included (about 40 MB).

**Verdict.**

- **Use uBO Lite in complete mode** for now. It blocks as well as full uBO here (same adblock-tester score, no
  YouTube ads), needs no patch, and runs under the stock 192 MB V8 heap. It costs about 4 % of Speedometer and
  0.6 s on Wikipedia.
- **Optimal mode** is the fast fallback: Speedometer is unchanged, Wikipedia is 0.2 s slower, and it misses 5 more
  adblock-tester points.
- **Full uBO has no advantage** that shows in these tests. It needs patch 0104 and a 320 MB V8 heap (see
  below), holds about 145 MB in its extension process, and let a 6 s pre-roll through once, right after launch.
- **adblock-rust** would cut the blocker's own memory. TV numbers: see "adblock-rust on the TV". With many heavy
  tabs that gain disappears: the ads a blocker stops cost as much as the blocker (see "Many tabs"). Building it in
  is a browser-side project (network hook, cosmetic filtering, scriptlets, list updates). Not worth it for
  memory alone.

## Method

- **Build.** `com.viiees.cr151b`: own speed build with patches 0103 and 0104 (0104 lets MV2 extensions run, see
  below), the omnibox trim and HistoryFuzzy. Installed for these runs.
- **Extensions.** Official release zips, unpacked into the app's data folder (`data/ab/{ubol,ubo}`), owned by the
  app's uid, loaded with `--load-extension` in browser.flags. Default lists, no changes.

  | Extension | File | sha256 |
  |---|---|---|
  | uBlock Origin 1.76.4 | `uBlock0_1.76.4.chromium.zip` (GitHub release) | `4b1b27ed82e734d508ae6d255933c334f62f256e8a8aece92724b826828e3d5f` |
  | uBO Lite 2026.1116.1650 | `uBOLite_2026.1116.1650.chromium.zip` (GitHub release) | `67e084b34470c51c08fa9314b118b8cb73df3a72e90c6a3b536d041c92e61bbc` |

- **uBO Lite mode** is set before each run from its dashboard page over CDP
  (`setDefaultFilteringMode`, 2 = optimal, 3 = complete). Host permission `<all_urls>` is in its manifest.
- **Every variant runs with a 320 MB V8 heap** (`--js-flags=--max-old-space-size=320`), so the variants differ
  only in the blocker.
- **Script:** `bench/adblock_run.py`. Every case is a fresh launch on a local page, then the case's page in the
  same tab. Screensaver kept off with `bench/keepawake.sh`.
- **Pages.**
  - Wikipedia: the local harness case `load-wiki`.
  - News: `https://www.dailymail.co.uk/home/index.html`, live, so its own variance is part of the result.
    It never fires `load` on this TV. The script counts over a fixed 60 s window from CDP Network events.
  - adblock-tester: `https://adblock-tester.com/`, score from `.final-score`.
  - YouTube: `dQw4w9WgXcQ` and `kJQP7kiw5Fk`, played from the page with a user gesture.

Raw files:

- `adblock_score.txt`: adblock-tester;
- `adblock_effect.txt`: YouTube, and the uBO warm-up. Its score lines come from an older parser and are wrong;
- `adblock_load.txt`: Wikipedia. Its `news` lines are from the old `load`-based probe, all timeouts;
- `adblock_news.txt`: news page, 60 s window. Round 1 of "none" (DCL 1.8 s, load 1.8 s) did not reload the page
  and is excluded: the no-blocker median is of rounds 2–3;
- `adblock_speedometer.txt`;
- `adblock_rust_host.txt`, `adblock_rust_tv.txt`: adblock-rust benches.

## Details

### Effectiveness

- **adblock-tester.** uBO Lite optimal 91, complete 96, uBO 96, out of 100 (11 services, 22 checks). No failed
  service is listed in any variant. The difference between 91 and 96 is in partial checks.
- **YouTube.** Without a blocker every sample was an ad. uBO Lite (both modes): no ad. uBO: a 6 s pre-roll on the
  first video, the first launch after start-up, then none.
- **News page.** Blockers cut DOMContentLoaded from about 48 s to 37–40 s. The window counts only requests of
  the main frame's process. Ads in cross-site iframes run in other processes and are not counted. Bytes are not
  comparable: the profile's disk cache serves most of the page after the first run.

### Performance and memory

- **Speedometer.** uBO Lite optimal costs nothing measurable. Complete costs about 4 % and full uBO about 2.5 %.
  Complete injects more scripts into each page, so the cost is plausible. Judgement, not profiled.
- **Wikipedia.** The first no-blocker round (5.0 s) is the first page load after the variant switch. The medians
  skip that effect.
- **Memory.**
  - uBO Lite has its rules in the browser process (declarativeNetRequest): about +30 MB there. Its service worker
    adds about 85 MB while it runs, then Chrome stops it. On the news page it was already stopped.
  - uBO keeps a background page all the time: about 145 MB above TV Tools.

### Many tabs

`adblock_run.py tabs`: a heavy news or shopping page in a new tab every 45 s (10 sites in turn), until the browser
or the TV gives up. One run per variant, so treat the numbers as a first look. Raw: `adblock_tabs.txt`.

| Variant | Tabs open when it failed | How | All chrome RSS at 10 tabs |
|---|---|---|---|
| No blocker | 16 | browser killed and restarted, all tabs gone | 1 002 MB |
| uBO Lite complete | 19 | the same | 974 MB |
| uBlock Origin | 14 | the whole TV restarted (power-on reason `micomPower`) | 1 027 MB |

- **The blocker's fixed cost is paid back by the ads it stops.** With one page uBO Lite adds about 135 MB. With 10
  heavy pages the totals are within 5 % of each other, and uBO Lite is the lowest.
- **The ceiling is about 15–19 heavy tabs** in every variant. Before that, zram swap fills (SwapFree near 0) and
  pages that are still loading stop answering for 20 s and more.
- **Order bias.** The no-blocker run went first, with zram already two-thirds full from earlier work (SwapFree 189
  MB against about 320 MB for the others). That alone could cost it a few tabs.
- **The kill is not logged.** The logs from before the TV restart were lost. The 2026-11-11 memchute pattern (see
  FINDINGS) is the likely cause of the browser restarts, but this run does not prove it. Nobody touched the
  TV during the uBO run (the owner confirmed), so the TV restarted by itself under memory pressure, probably a
  watchdog reset. The exact trigger was not logged.

So a native engine would not raise the tab ceiling noticeably. Its memory gain is only visible with one or two
tabs, where memory is not short anyway.

### Problems found

- **Full uBO dies under the stock heap.** run.sh sets `--max-old-space-size=192 --optimize-for-size`. The uBO
  background page hits "V8 javascript OOM (Reached heap limit)" about 2 minutes after start, and blocking stops.
  With 320 MB it survived a 5-minute warm-up. `browser.flags` cannot carry a space inside a value, so a variant
  with its own `--js-flags` loses `--optimize-for-size`.
- **MV2 is gated in M151 by one function.** `ShouldDisableLegacyExtensions()` in
  `extensions/browser/manifest_v2_handler.cc`. Patch `patches/0104-allow-mv2-extensions.patch` makes it return
  false. It is in the cr151b build. It is not committed yet, and every build from this tree now includes it.
- **adblock-tester crashes the tab without a blocker:** "Aw, Snap!", error 11, with Dawn/WebGPU adapter
  warnings in the log. With a blocker the page loads. Not investigated: probably a script that a blocker stops
  reaches WebGPU.
- **The slow YouTube playback in these runs was a test artifact** (an ad advanced about 14 s per 60 s, content
  2–4 s). The cr151b profile had no Google consent cookie. YouTube's consent lightbox comes 10–15 s after the
  page, after the script had looked for it, and the page pauses the player while the lightbox is open. Answered,
  playback runs at 1× in every build (`video_cr151p.txt`, `ytplay_consent.txt`, FINDINGS "YouTube playback").
  The ad counts stand: a stuck ad inflates the no-blocker "40 / 40", but the blockers showed no ad at all.

## adblock-rust on the TV

Brave's engine, built from `brave/adblock-rust` at `1108c61472dd5a29ae56388ee936048c4fe5a69f` with its own
criterion benches, for `armv7-unknown-linux-gnueabi` (the same target as Chromium's Rust). Toolchain: Rust
nightly-2026-06-17, `zig cc` as C compiler and linker (glibc 2.17, cortex-a7, NEON, softfp). Lists are the repo's
snapshots: EasyList, EasyPrivacy, and `brave-main-list.txt` (197k lines, uBO filters included).

| Bench (criterion, 10 samples) | TV | Host |
|---|---|---|
| Match 242 944 real requests, browser-like, Brave list | 13.9 s = 57 µs per request | 0.84 s = 3.5 µs |
| The same, EasyList + EasyPrivacy | 8.6 s = 35 µs per request | 0.61 s = 2.5 µs |
| First request on a fresh engine, Brave list | 8.7 ms | 0.62 ms |
| Engine memory, Brave list: after load / peak while building | 9.2 MB / 30.8 MB | same |
| Load a serialized engine, EasyList + EasyPrivacy | 22 ms | 0.62 ms |
| Serialize it | 20 ms | 0.55 ms |

Host column: aarch64 Docker on the build Mac, same benches, for scale. Raw: `adblock_rust_tv.txt`,
`adblock_rust_host.txt`.

What it means for a native blocker:

- **Matching is cheap.** A heavy page makes about 200–300 requests, so the Brave list costs 11–17 ms of one A55 core
  per page, spread over the load. uBO Lite's declarativeNetRequest is also native, so request blocking alone is not
  where the extensions lose speed. Their cost is the cosmetic and scriptlet work in each page.
- **Memory is the real gain:** about 9 MB resident for the whole Brave list, against 115–145 MB for the extensions
  here. Building the engine peaks at 31 MB. Loading a pre-serialized engine takes about 22 ms.
- **The engine alone does not block YouTube ads.** YouTube needs scriptlets and cosmetic rules that adblock-rust
  only returns. The browser has to inject them, as Brave does. Judgement from Brave's design, not tested here.

## Built into the cr151 package

`package.sh` ships uBO Lite with the browser, in complete mode on a fresh profile.

- **Source.** The official release zip, `uBOLite_2026.1116.1650.chromium.zip` from
  <https://github.com/uBlockOrigin/uBOL-home/releases>, in a `.adblock/ubol/` folder next to the repository. The
  package step mounts it read-only (`-v "$PWD/../.adblock:/adblock:ro"`) and fails on a sha256 mismatch.
- **Loading.** The zip is unpacked to `browser/ext/ubol`. At launch run.sh copies it to the data folder
  (`$S/ext/ubol`, refreshed when the uBO Lite version changes) and `--load-extension="$EXT"` becomes
  `"$EXT,$UBOL"`. Chrome keeps only the last `--load-extension`, so the list must stay one. The build fails if the
  edit does not apply.
  - Why the copy: Chrome writes the indexed declarativeNetRequest rulesets into an unpacked extension's own
    `_metadata/`. From the read-only app folder it dropped uBO Lite without an error: no service worker, and its
    pages showed `ERR_BLOCKED_BY_CLIENT`. TV Tools runs from a data-folder copy for the same reason.
- **Complete mode.** `js/mode-manager.js` ships `defaultFilteringModes` with `all-urls` under `complete` instead
  of `optimal`.
  - Why this way: uBOL's own switch is the managed-storage policy `defaultFiltering`. Chrome on Linux reads it
    only from a policy file under `/etc`, which is read-only on the TV. A policy would also lock the choice.
  - The changed default applies only until the user picks a mode in uBOL's settings.
  - uBOL drops to basic only when it lacks broad host permissions. Its manifest asks for `<all_urls>`, and an
    unpacked extension gets them.

## Licenses

uBlock Origin and uBO Lite are GPLv3, adblock-rust is MPL-2.0. uBO Lite ships in the cr151 IPK (see
THIRD_PARTY_NOTICES.md). None of them is stored in the repository.
