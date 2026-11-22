# Roadmap

Open work in priority order. The status of each item is current as of 2026-11-21.

## 1. Chromium TV: our WebOS-Chromium 151 build

Shipped as `com.viiees.chromiumtv` ("Chromium"), rebased onto WebOS-Chromium 1.0.0 on 2026-11-21. Speedometer 0.748
after the rebase, 0.737 before it (`cr151/rebase_speedometer.txt`). The build history and numbers are in `cr151/RESULTS.md` and
[FINDINGS.md](FINDINGS.md).

- **Our patches on 1.0.0:** 0102–0104, 0107, 0109 and 0110 (0110 built, not installed yet). The others went upstream: see the upstream table in
  [FINDINGS.md](FINDINGS.md#8-upstream-candidates).
- **Rebase recipe.** Replace `cr151/upstream/source` with `git archive <sha> source` of WebOS-Chromium, record the
  commit in `cr151/upstream/COMMIT`, then run the `incontainer.sh` steps `patch`, `gen`, `build chrome` and `package`.
  With the same Chromium version the rebuild is incremental. After a rebase, rerun the harness, the video test and
  the omnibox A/B (`bench/uilat.py`). Compare interleaved runs only: the TV's round-to-round spread is about 40 ms.
- **Open:** a second build with their exact args for a byte-level trust check (needs the owner's go), PGO.

## 2. Input latency

Measured with Chromium's own histograms (`cr151/UI_LATENCY.md`, `cr151/INPUT_LATENCY.md`).

- **Omnibox.** Done. The trim (fewer providers and rows, suggest after a pause, no ML scoring or AI Mode) is on by
  default, and `omnibox=full` in `media.opts` turns it off. Patch 0109 removes the slowdown that upstream 0058 brought:
  key to screen 87–107 ms, paint to present 25–35 ms (was 160 ms on 0.0.66).
- **Arrow keys in pages.** Patch 0103 takes Down from 167 to 115 ms. Left: the spatial-navigation walk over all
  elements, about 80 ms on a long page. Next step, if wanted: skip offscreen locked sections (this changes which
  elements are candidates).
- **GPU off by a crash.** Found 2026-11-22: every exit with the GPU on crashed (the Mali driver's destructor touches
  the already closed Wayland display in `exit()`), and the launcher then turned the GPU off for every later start
  (`data/gpu.state`). Patch 0110 exits with `_exit()`; built with the autoconsent change below (IPK sha256 `7b65d4d6…`), not installed. Next: install
  it, delete `data/gpu.state`, confirm with `bench/gpuexit.py` that exits end with status 0, then report upstream: their
  launcher has the same rule.
- **autoconsent while scrolling.** Its CMP detection retries rescan the DOM during the scroll. A test build whose
  retries wait for 1 s without wheel, scroll or keys (`acidle`) halves the cost: rAF 26 ms against 53 ms, Long Animation
  Frames 66 against 123 ms per notch (no autoconsent: 18 ms and 8 ms). Next: confirm it still rejects, then ship it
  through `cr151/autoconsent.sh`.
- **Wheel scrolling.** `--disable-smooth-scrolling` ships. Its measurements (notch 142 ms on Wikipedia, was 196) were
  made with the GPU off, so the choice needs a recheck with the GPU on. On heavy sites the page's main thread is the
  limit.
- **Late frames.** Closed: the ~90 % was v4 reading late evdev timestamps, plus software mode. With the GPU on the
  compositor drops 0–4 % of frames.
- **YouTube.** With the TV user agent, `youtube.com/tv` redirects to the desktop site, so there is no TV interface.

## 3. Smaller gaps

- **HEVC.** Plays through NDL, 4K included (upstream 0055, our PR #20). HDR colours are not checked.
- **Cookie banners.** autoconsent (lean-frames) rejects 7 of 11 tested banners. `bench/consent_run.py` was changed
  for the packed uBO Lite. Only its setup was checked on the TV, not a full run.
- **Upstream PRs waiting:** WebOS-Chromium #22 (fonts.conf, waits for the owner's tests on webOS 4, 5 and 10) and #27
  (0109 as their 0062). See [FINDINGS.md](FINDINGS.md#8-upstream-candidates).
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
