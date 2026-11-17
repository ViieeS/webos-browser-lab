# Benchmarks: method and results

All numbers come from one TV. The device and every pinned version are listed in [SOURCES.md](SOURCES.md): an LG OLED55C1RLA on webOS TV 6.5.3, rooted, with 4x Cortex-A55, a Mali-G51, 32-bit armv7 softfp userspace and an aarch64 kernel 4.4.
They were measured on 2026-11-11 .. 2026-11-17 with the tools in [`bench/`](../bench).

## Final comparison

| Case | WebOS-Chromium 151 (0.0.66) | Chromium 120 OSE (cr120) | WPE WebKit 2.52.6 | Stock LG browser (Chromium 87) |
|---|---|---|---|---|
| micro (JS loop, math, objects, strings; ms, lower is better) | 340-345 | 259-309 | 225-245 | 334-372 |
| load-wiki (local Wikipedia page, loadEventEnd) | 3.5-3.7 s | 3.1-3.3 s | 2.9-3.1 s | 4.8-5.1 s |
| raf-wiki (rAF-driven scroll, fps) | 62-63 | 61 | 21-28 | 57-59 |
| Speedometer 3.1 | 0.73-0.76 | 0.58-0.60 | 0.80-0.84 | does not start |
| YouTube home load | 5.3-6.1 s (CDP, warm cache) | 7.6-8.3 s (CDP, warm cache) | 9.5-10.2 s (host load event) | not measurable |
| Video | hardware (NDL), up to VP9 2160p, 0 dropped frames | hardware (NDL, same code) | software only, ~14 fps at H.264 1080p30 | — |
| DRM (EME key systems) | ClearKey | ClearKey | none | not measured |

Ranges are min-max over 2-4 runs. WPE is the final build: a55 + patches 0013-0015 + mimalloc.

### Where each number comes from

| Engine | Page cases (micro, load-wiki, raf-wiki, Speedometer) | YouTube | Video |
|---|---|---|---|
| cr151 own build | `cr151/harness_cr151own.txt` (interleaved with 0.0.66) | `cr151/youtube_cr151own.txt` | `cr151/video_cr151own.txt` |
| cr151 | `cr151/harness_cr151.txt` | `cr151/RESULTS.md` (cdpnav.py runs, the raw console output was not kept) | `cr151/video_cr151.txt` |
| cr120 | `cr120/harness_cr120_swraster.txt`. GPU-raster runs: `cr120/harness_cr120.txt` | `cr120/RESULTS.md` (cdpnav.py, raw output not kept) | `cr120/video_cr120.txt` (software), `cr120/video_neva.log` (uMediaServer), `cr120/video_ndl.log` (NDL) |
| WPE | `bench/results/mi-mimalloc-clean.jsonl` (4 rounds), `bench/results/default-mi.jsonl` | `cold-youtube` in the same file: the host's load event, not CDP | Video was run in WPE on 2026-11-16, but its raw output was not kept. The summary is in [FINDINGS.md](FINDINGS.md) |
| Stock | `cr151/harness_cr151.txt` (control rows), `build/harness-stock.log`, `build/stock-speedo.log` | — | — |

The decisions per WPE patch were based on these files:
- `build/ab-*.sh` (the command lines run);
- `build/ab-*.log` (their output);
- the matching `bench/results/<label>.jsonl` records.

Every jsonl record carries the library and host md5 and a timestamp.
cr120 uses software raster (`--disable-gpu-rasterization`), because GPU raster drew images as green boxes on Mali.
cr151 renders with GPU raster.

### Caveats that change how to read the table

- **Viewports differ.**
  - cr151 renders in its browser UI at device scale 1.5: 1280x720 DIP minus the toolbar.
  - content_shell (cr120) renders 1920x1080 at scale 1.
  - WPE renders full screen.
- **cr151 is a size-optimised build:** `optimize_for_size`, LTO without optimisation, no PGO.
  - Overriding `--js-flags` changed nothing in micro (332-357 ms).
  - Tested 2026-11-17 with an own speed build (`cr151/args.delta.gn`): load-wiki 2.7-3.1 s, Speedometer 0.83-0.85, micro 306-370 ms. The flags explain the load and JS gap, not micro. See `cr151/RESULTS.md`.
- **YouTube sends different user agents.**
  - WPE: a desktop Safari UA.
  - cr120: Chrome 120.
  - cr151: a webOS TV UA, set by its TV Tools extension.

  So the page payload may differ. All runs: no login, consent rejected, warm disk cache.
- **The stock browser cannot be instrumented.** It runs inside a jail, and ls-hubd rejects a wrapped executable (error -1027). That is why the harness below reports through an HTTP beacon instead of DevTools.

## Method

### Ground rules

- **Pages and suites are served from the TV itself.**
  - The server is the TV's own `/usr/sbin/lighttpd` with [`bench/lighttpd.conf`](../bench/lighttpd.conf): 127.0.0.1:8099, document root `/media/developer/bench`.
  - This takes the network out of every local case.
  - Only the `YouTube` and `cold-*` cases use the internet.
- **One fresh browser launch per run.**
  - Before each launch the harness closes every browser and `youtube.leanback.v4`. webOS preloads them in the background, and they take ~140 MB of RAM. After a boot, the stock browser can sit at ~240% CPU.
  - A run under that load is void.
- **Do not let the TV screensaver start mid-run.**
  - It is a media pipeline (4K HEVC) and takes CPU and decoders.
  - Runs that overlapped it were dropped. Each RESULTS file notes which.
- **Never measure with the WebKit inspector or DevTools attached** when per-frame layout or paint matters. An attached Timeline inflates both.
  - Use the inspector to find suspects, then confirm without it: perf, beacons, or an env-gated backtrace.
  - Load times through CDP (`cdpnav.py`, `navtime.py`) are fine. They read `performance` entries once at the end.
- **One user of the TV at a time.**
  - Two people benchmarking at once close each other's browsers.
  - Runs that overlapped were excluded by the timestamps in the access log.
- **Fingerprint every A/B.** `bench.py` records the md5 of the WebKit library and of the host binary, MemAvailable before the run and the boot time with every record.

### Cross-browser harness (`bench/harness_run.py` + `bench/pages/harness.html`)

- `harness.html?case=<case>&tag=<browser>&run=<n>` loads the test page into a same-origin full-screen iframe.
- It reports with `GET /beacon?...`. lighttpd's access log (`/tmp/bench-access.log`) is the result channel. This works in any browser, including the stock one.
- `harness_run.py -b stock,ours,cr120,cr151 <rounds> <case...>` launches each browser through `luna://com.webos.applicationManager/launch` with the page URL. cr120 launches through its `run_tv.sh`.
- The script then polls the log for the beacon until a per-case ceiling, closes the browser and prints one line per run.
- Browsers alternate inside each round, so drift over time hits all of them equally.

| Case | What it measures |
|---|---|
| `micro` | `host/bench.html`: four JS kernels (int loop, math, objects, strings), best of 3 each, with checksums. Total in ms. |
| `load-wiki` | A local snapshot of en.wikipedia.org/wiki/Television (`bench/pages/wiki`). Reports loadEventEnd. |
| `raf-wiki` | After load + 2 s, a 10 s `requestAnimationFrame` loop that scrolls 8 px per frame. Reports frames per second, that is how often the page's main thread gets a frame while it scrolls. |
| `raf-wiki-nojs` | The same with the iframe sandboxed (page scripts off). Separates page scroll handlers from engine cost. |
| `raf-wiki-nosticky`, `raf-long` | Diagnostics: sticky/fixed elements made static, images or scrollers removed (`rm=`, `noimg`). A synthetic long page with a static or sticky box. |
| `settle-wiki(-nojs)` | How long the main thread stays busy after load: the last rAF gap over 100 ms, and the sum of gaps over 50 ms within 12 s. |
| `speedometer` | Speedometer 3.1, `?startAutomatically&iterationCount=2`, the score from `#result-number`. |

### Single-engine A/B (`bench/bench.py`, WPE only)

- `bench.py run --label L [--repeat N] [case | @local | @net | @all]` launches our WPE app with launch params.
- It parses the host log (`LOAD`, `BENCH`, `SCROLL`, `PROBE`, `CRASH`, ...) into `bench/results/<label>.jsonl`.
- `bench.py compare A B` prints medians, spread, delta and a permutation p-value.
- Cases: micro, mathfold, speedometer, jetstream-js, motionmark, load-wiki, wheel-wiki(-settled), raf-wiki, cold-google, cold-wiki, cold-youtube, nav-google-wiki and wheel-youtube(-settled).
- The `build/ab-*.sh` scripts and their `.log` files are the A/B runs behind each WPE patch decision: -mcpu, allocator, patches 0013-0015 and mimalloc.

### Page load over DevTools

- `bench/navtime.py` (WebKit inspector) and `bench/cdpnav.py` (Chrome DevTools Protocol) navigate to a URL. After a wait they read `loadEventEnd`, FCP and an optional element count.
- They reconnect after a cross-site process swap.
- DevTools ports are opened only for the run and bound to the TV's LAN address, never 0.0.0.0. M151 binds DevTools to 127.0.0.1 only, so cr151 runs used a temporary TCP relay (`bench/tcprelay.c`), removed after.

### Video (`bench/video_run.py` + `bench/pages/video.html`)

- **Clips.** `bench/media/gen.sh` makes 20 s synthetic clips (ffmpeg testsrc2):
  - H.264 1080p30 and 1080p60;
  - HEVC 2160p30;
  - VP9 1080p60 and 2160p30;
  - AV1 1080p30;
  - a fragmented H.264 file for MSE;
  - H.264 + AAC.

  They are uploaded to `/media/developer/bench/media`.
- **Capabilities.** `video.html?caps=1` reports canPlayType, `MediaSource.isTypeSupported` and EME key systems: Widevine, PlayReady, ClearKey.
- **Playback runs.** Each clip plays for 15 s, either as `<video src>` or through MSE with 2 MB appends, the way players feed segments.
  - The page reports played seconds, total and dropped frames from `getVideoPlaybackQuality()`, stalls (`waiting` events) and the decoded size.
  - `video_run.py` samples per-thread CPU over 8 s of playback (jiffies, 800 = one core). The thread names tell hardware from software decode: for example FFmpeg `Media` threads or libvpx workers versus a near-idle renderer.

### Profiling

- `perf/build_perf.sh` builds a static `perf` from linux-4.4.302 tools/perf. The armv8_pmuv3 counters work on the C1.
- `perf/perfsym.py` records the web process and symbolizes it with addr2line against an unstripped library from the build volume.
- `bench/timeline.py`, `wheeltl.py` and `layers.py` drive the WebKit inspector Timeline and layer tree. They are only for finding suspects, see the ground rules.

## Running it

1. **Root and telnet.** Root the TV (RootMyTV or similar). The harness reaches it over telnet as root without a login.
2. **Point the scripts at the TV.** `export TV_HOST=<tv ip>`. Every script requires it.
3. **Copy the test pages to the TV.** Put `bench/pages/` and `host/bench.html` at `/media/developer/bench/pages/`. `host/tvstream.py <tv> <file> <remote>` streams files over telnet.
4. **Add the benchmark suites.** Fetch Speedometer 3.1, JetStream 3.0 and MotionMark 1.3.2 from their WebKit GitHub release branches into `/media/developer/bench/{speedometer3.1,jetstream3.0,motionmark1.3.2}`. They are not in this repository.
5. **Generate the clips.** Run `bench/media/gen.sh` and upload the clips to `/media/developer/bench/media`.
6. **Run the harness.** For example `bench/harness_run.py -b stock,cr151 3 micro load-wiki raf-wiki`. It starts lighttpd on the TV if it is not running.
