# Roadmap

Open work in priority order. The status of each item is current as of 2026-11-23.

## 1. Chromium TV: our WebOS-Chromium 151 build

Shipped as `com.viiees.chromiumtv` ("Chromium"), rebased onto WebOS-Chromium 1.1.0 (`6071897`) on 2026-11-23 and
installed with the owner's yes. Speedometer with the GPU on: 0.781–0.799 on 1.1.0 (`cr151/speedometer_110.txt`),
0.756–0.779 on 1.0.0, and 0.725–0.731 with the GPU off (`cr151/speedometer_gpu_on.txt`, `_off.txt`; the GPU costs ~80
MB more browser memory). After the 1.1.0 install: exits with the GPU on end with status 0, the GPU probe passes on a
normal start, autoconsent still rejects, omnibox key to screen 99–104 ms, and 1.1.0's V8 lite mode stays off on the C1
(747 MB free at start). The build history and numbers are in `cr151/RESULTS.md` and [FINDINGS.md](FINDINGS.md).

- **Our patches on 1.1.1:** 0102–0104 and 0107. 0109 is their 0062 since 1.1.0, 0110 their 0066 since 1.1.1. The others went upstream: see the upstream table in
  [FINDINGS.md](FINDINGS.md#8-upstream-candidates).
- **Rebase recipe.** Replace `cr151/upstream/source` with `git archive <sha> source` of WebOS-Chromium, record the
  commit in `cr151/upstream/COMMIT`, then run the `incontainer.sh` steps `patch`, `gen`, `build chrome` and `package`.
  With the same Chromium version the rebuild is incremental. After a rebase, rerun the harness, the video test and
  the omnibox A/B (`bench/uilat.py`). Compare interleaved runs only: the TV's round-to-round spread is about 40 ms.
- **Rebase onto 1.1.1** (released 2026-11-24, tag `1b4d053`): done, installed 2026-11-25 with the owner's yes. GPU
  on (the probe passed, the new launcher build id reset `data/gpu.state`), Back and menu > Exit end with status 0
  (`cr151/gpuexit_111.txt`), autoconsent rejects on IKEA, Cookiebot, BBC and YouTube
  (`bench/results/consent/shipped_111.txt`), omnibox key to screen 101–108 ms, paint to present 35–36 ms
  (`cr151/uilat_omnibox_111.txt`). Their 0066 is our 0110 hunk for hunk, so our series is 0102–0104 and 0107. The rest of 1.1.1 is a launcher
  change for webOS 4 (LG's buffered player through ACB): on webOS 5+ it stays off unless `media.opts` has `smp=direct`,
  so the C1 runs the same code paths. IPK sha256 `6ad253c1…`, copy in `browser/build/ipk-1.1.1/`.
- **Open:** a second build with their exact args for a byte-level trust check (needs the owner's go).
- **PGO.** Checked 2026-11-25 (FINDINGS): no arm32 Linux profile exists. The x64 Linux profile (88 MB download, needs
  the owner's yes) would cover only the code that is the same on arm32, and a full rebuild follows. Our own profile
  needs a clean exit, which 0110 removes. Not started.

## 2. Input latency

Measured with Chromium's own histograms (`cr151/UI_LATENCY.md`, `cr151/INPUT_LATENCY.md`).

- **Omnibox.** Done. The trim (fewer providers and rows, suggest after a pause, no ML scoring or AI Mode) is on by
  default, and `omnibox=full` in `media.opts` turns it off. Patch 0109 removes the slowdown that upstream 0058 brought:
  key to screen 87–107 ms, paint to present 25–35 ms (was 160 ms on 0.0.66). Rechecked 2026-11-22 with the GPU on:
  105–108 ms and 34–36 ms; with the GPU off 168–173 ms and 135–136 ms (`cr151/uilat_omnibox_gpu.txt`).
- **Arrow keys in pages.** Patch 0103 takes Down from 167 to 115 ms. Left: about 80 ms per key inside the
  handler on a long page. Patch 0111 (skip offscreen locked sections) cut the visited elements by 30 % with the same
  focus, but the time only by about 4 ms, so it is shelved (`cr151/UI_LATENCY.md`). The cost is outside the per-element
  visit. Next step, if wanted: a sampling profile of the renderer during arrow keys.
- **GPU off by a crash.** Fixed 2026-11-22: every exit with the GPU on crashed (the Mali driver's destructor touches
  the already closed Wayland display in `exit()`), and the launcher then turned the GPU off for every later start
  (`data/gpu.state`). Patch 0110 exits with `_exit()`; installed (IPK sha256 `7b65d4d6…`), and Back and menu > Exit
  now end with status 0 (`cr151/gpuexit_0110.txt`). `data/gpu.state` deleted with the owner's yes: the GPU probe passed
  and a Back exit 50 s after start left no new file. Sent upstream as PR #30 (their 0066), 2026-11-22.
- **autoconsent while scrolling.** Done 2026-11-22: its CMP detection retries wait for 1 s without wheel, scroll or
  keys. rAF frames 26 ms against 53 ms during a Wikipedia scroll (no autoconsent: 18 ms). The installed build still
  rejects on IKEA, Cookiebot, YouTube and Google (`bench/results/consent/shipped_0110.txt`).
- **Wheel scrolling.** `--disable-smooth-scrolling` ships, rechecked with the GPU on (2026-11-22): no difference on
  Wikipedia, and better on reddit (first notch 18 against 193 ms) and YouTube (rAF 174 against 234 ms). On heavy sites
  the page's main thread is the limit.
- **Late frames.** Closed: the ~90 % was v4 reading late evdev timestamps, plus software mode. With the GPU on the
  compositor drops 0–4 % of frames.
- **YouTube.** Closed 2026-11-24: `youtube.com/tv` keeps its TV interface. Launched straight onto `/tv`, only a new
  profile's first starts went to the desktop site (3 of 4), then 12 of 12 TV (`cr151/ytua_launch_110*.txt`). No fix
  unless it shows up on the owner's profile; it would belong in TV Tools, not `--user-agent` in `run.sh`.
- **TV versions of other sites.** Checked 2026-11-25 on 20 sites (FINDINGS): only `youtube.com/tv` has one. Spotify
  turned into a mobile landing page with the TV user agent. Fixed 2026-11-25: `spotify.com` is in the default
  `desktopSites` (`package.sh`).
- **Dark theme.** On by default since 2026-11-25, switchable in TV Tools (FINDINGS, "Dark theme against OLED wear").
  Measured 2026-11-25: On and Off are the same for arrow scrolling, Tab focus and dropped frames
  (`cr151/darktheme_ab.txt`), but with the GPU off (`data/gpu.state`). Not rechecked with the GPU on.

## 3. Smaller gaps

- **HEVC.** Plays through NDL, 4K included (upstream 0055, our PR #20). HDR colours are not checked.
- **Cookie banners.** autoconsent (lean-frames) rejects 7 of 11 tested banners. Rechecked on the installed 1.1.0 over
  all 14 sites (2026-11-24, `bench/results/consent/shipped_110_all.txt`): every consent record matches the lean-frames
  run. Rejected: IKEA, Cookiebot, Booking, Usercentrics, BBC, YouTube, Google. The rest need no fix (screenshots of the
  2026-11-20 lean-frames run): Guardian, Mirror, Amazon and reddit show no banner, Independent shows a membership
  pop-up, not a cookie banner. Only 20minutes blocks the page: its Didomi banner is consent-or-pay ("Refuser et
  s'abonner"), and autoconsent's Sourcepoint rule likewise stands back when a subscribe button is there. No free
  reject exists, so nothing is clicked and no consent is stored. The owner chose to hide them (2026-11-25): our
  autoconsent rule hides Didomi's consent-or-pay banner and unlocks scrolling, checked on the TV from a temp folder
  ([FINDINGS.md](FINDINGS.md)). Installed 2026-11-25 (`bench/results/consent/shipped_110_cop.txt`). A Sourcepoint consent-or-pay rule waits for a site
  that shows one.
- **Upstream PRs waiting:** WebOS-Chromium #22 (fonts.conf, waits for the owner's tests on webOS 4, 5 and 10) #27
  (0109 as their 0062) and #30 (0110 as their 0066). #27 merged into their 1.1.0, #30 into their 1.1.1 (2026-11-24). See [FINDINGS.md](FINDINGS.md#8-upstream-candidates).
- **Upstream the WebKit fixes** listed in [FINDINGS.md](FINDINGS.md#8-upstream-candidates):
  - the ARMv7 RegExp JIT fixes (0010-0012);
  - SystemHeap alignment (0013);
  - the ARMv7 CSS JIT (0015).
- **DRM is not solvable.** Widevine is not available as a Chrome CDM on the TV. PlayReady is API-compatible but untested.
- **Tab memory ceiling.** Done 2026-11-19: `package.sh` sets TV Tools' tab limit to 8, so the oldest tab closes above
  8 ([TRIM_CANDIDATES.md](../cr151/TRIM_CANDIDATES.md#results-2026-11-19)).

## 4. Housekeeping

- The `cr120` volume and image were deleted on 2026-11-17. See [ARTIFACTS.md](ARTIFACTS.md).
- Keep [ARTIFACTS.md](ARTIFACTS.md) current: the bisect app `com.viiees.cr151p` was removed on 2026-11-21.
