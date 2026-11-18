# Roadmap

Open work in priority order. The status of each item is current as of 2026-11-17.

## 1. Own WebOS-Chromium 151 build: built and measured

Result 2026-11-17 (`cr151/RESULTS.md`): installed as `com.viiees.cr151`. Speedometer +14 % and wiki load -20 to -30 % against 0.0.66. micro unchanged, still behind cr120. Open: a second build with their exact args for a byte-level trust check (needs the owner's go), PGO.

- **Build.** Build WebOS-Chromium from source at commit `1499d397`:
  - natively on the arm64 host;
  - clang 23.1.6 from apt.llvm.org and rustc nightly 2026-06-16;
  - see `cr151/Dockerfile`.
- **Speed config** (`cr151/args.delta.gn`):
  - no `optimize_for_size`;
  - full ThinLTO with optimisation;
  - `-mcpu=cortex-a55` if the toolchain allows it.
- **Patch 0100.** On webOS, no window caption buttons. The window is always full screen, and "minimize" leaves the user with no way back.
- **Packaging.** Ship it as a separate dev app, `com.viiees.cr151`, next to the upstream release.
- **Measure** with the full set from [BENCHMARKS.md](BENCHMARKS.md) against 0.0.66 and cr120.
- **Check trust.** Compare the build with the release binary: libraries, exported symbols, strings, section sizes. A bit-exact comparison needs a second build of their exact config.
- **Done when** the speed build closes the micro and load gap to cr120, or proves that the build flags are not the cause.

## 2. Browser UI responsiveness

Measured 2026-11-17 (`cr151/UI_LATENCY.md`, Chromium's own histograms): the speed build is 14-25 % faster than
0.0.66, but a key in the omnibox still takes about 160 ms to the screen (about 60 ms of it after paint), and a Down
press in a page about 160 ms. The flags do not fix it. The stage split and A/B found two causes:
- In pages, `--enable-spatial-navigation` (their run.sh) costs about 125 ms of each arrow press: the candidate walk
  updates style and layout thousands of times per key. With it off, Down takes 36 ms, but arrows stop moving between
  links. Patch 0103 (2026-11-18) removes the per-element update: Down 167 → 115 ms, same focus moves. Left: the walk
  over all elements (about 80 ms on a long page). Next step, if wanted: skip offscreen locked sections (changes candidates).
- In the omnibox, the cost is the browser main thread (Views layout and paint, autocomplete), not GPU or flags.
  Software rendering is worse everywhere. The runtime trim (2026-11-18: fewer providers and rows, suggest after a pause,
  no ML scoring or AI Mode) takes a key from 160 to 87 ms. Next: ship it in run.sh if the owner agrees.

- **The problem.** The Chrome UI in cr151 feels slow with the remote.
- **What to measure:**
  - cold start to first paint;
  - key-to-paint latency in the omnibox and the tab strip;
  - focus movement.

  Compare the release build with the speed build.
- **If the build flags do not fix it, the options are:**
  - trim the UI (Chrome features and flags);
  - the webOS OSE `browser_shell` with Enact Browser ([webosose/com.webos.app.enactbrowser](https://github.com/webosose/com.webos.app.enactbrowser)). Its code is in the chromium120 tree under `neva/browser_shell` and is off by default;
  - a minimal own UI over content_shell with `--enable-spatial-navigation`.

## 3. Smaller gaps

- **HEVC.** The TV decodes it through NDL, but Chromium's mime check rejects it before the renderer.
- **Upstream the fixes** listed in [FINDINGS.md](FINDINGS.md#8-upstream-candidates):
  - the WebKit ARMv7 RegExp JIT fixes (0010-0012);
  - SystemHeap alignment (0013);
  - the ARMv7 CSS JIT (0015).
- **DRM is not solvable.** Widevine is not available as a Chrome CDM on the TV. PlayReady is API-compatible but untested.
- **Tab memory ceiling.** Every blocker variant fails at 15-19 heavy tabs, and once the whole TV restarted
  ([ADBLOCK.md](../cr151/ADBLOCK.md#many-tabs)). Cap the tab count or discard background tabs before zram fills.
  After the current tasks.

## 4. Housekeeping

- The `cr120` volume and image were deleted on 2026-11-17, after item 1 was measured. See [ARTIFACTS.md](ARTIFACTS.md).
- When a newer WebOS-Chromium release appears, rerun the harness and the video test on it.
