# Build artifacts: what existed, what was deleted, how to recreate

Binaries are not versioned. This page records:
- what each experiment produced;
- what was deleted when the frozen lines were closed on 2026-11-17;
- the command that recreates each item.

Results and conclusions from these artifacts are kept in the text files of this repository. The deletions remove only things that can be rebuilt.

## Deleted on 2026-11-17

### Build host

| Item | Size | Was used for | Recreate with |
|---|---|---|---|
| Docker volume `wpe-br64` | 22.7 GB | 64-bit path: aarch64 buildroot, WPE 2.52.6 aarch64, `jsc64own` | `buildroot64/build.sh`. The bridge build recipe is in [FINDINGS.md](FINDINGS.md#4-64-bit-path-frozen) |
| Docker volume `wpe-br` | 18.9 GB | WPE build tree (buildroot-nc4 @322ff04e, WebKit 2.52.6, gcc 16.2.0), plus `linux-4.4.302` (perf), `mimalloc-2.1.7`, `orig-cssjit` (pre-0015 sources) | `WEBKIT_MCPU=cortex-a55 buildroot/build.sh`, then `perf/build_perf.sh` and `mimalloc/build_mimalloc.sh` |
| Docker image `wpe-br` | 0.8 GB | Build environment for the above | `docker build -t wpe-br buildroot/` (`build.sh` does it) |
| `build/lib-*` | ~1 GB | One `libWPEWebKit` per A/B variant: a9, a9-p13, a9-p13v2, a55, a55-v2, a55-p13, a55-p14, a55-p14v2, a55-cssjit, and the unstripped `*-dbg.so` for perf/addr2line | Rebuild with the matching patch set and `WEBKIT_MCPU`. The patch for each label is named in `build/ab-*.sh` |
| `build/cores/` | 2.4 GB | Core dumps from the A55 SIGBUS (crash A, fixed by 0013) and the RegExp JIT crash (fixed by 0010-0012) | Not needed. The analysis is in FINDINGS |
| `build/app/`, `build/ipk-2.52.6*/`, `build/*.ipk`, `build/browser`, `build/hostonly/` | ~0.5 GB | Bundled WPE app and IPKs | `host/bundle.sh` + `host/make_ipk.py` |
| `build/wpe64*/`, `build/jsc32/`, `build/jsc64*/`, `build/MiniBrowser64` | ~0.7 GB | 64-bit WPE bundle, 32- and 64-bit jsc shells used for `build/jsall*.txt` | `buildroot64/` build. jsc64 is Debian trixie `libjavascriptcoregtk-bin` 2.54.0 arm64 |
| `build/tvlib/`, `build/gdbtv*` | small | TV system libraries for symbolization, gdb 16.3 for the TV | Copy from the TV with `host/tvfetch.py`. gdb notes are in FINDINGS (its breakpoints never fired in WebKit, so prefer perf) |
| `build/media/`, `build/suites.tgz`, `build/pages.tgz` | ~0.4 GB | Copies of the test clips and suites for upload | `bench/media/gen.sh`, and the suites from [SOURCES.md](SOURCES.md#benchmark-suites) |
| Compiler logs `build/br*.log`, `build/a55-*.log`, `build/a9-*.log` | — | Build output | Produced by every build |
| Docker volume and image `cr120` (deleted after the own cr151 build was measured) | 19 GB | chromium120 tree (webosose/chromium120 @e6a73fff), Debian buster sysroot, `out/` | `docker build -t cr120 cr120/`, then `cr120/sysroot.sh`, `cr120/build.sh`, `cr120/bundle.sh`. The last build is kept as `cr120/content_shell.gz` and `cr120/cr120.tar.gz` |

### TV

| Item | Size | Was used for |
|---|---|---|
| Spare `libWPEWebKit.*` variants in `com.viiees.browser/lib` | ~395 MB | A/B swaps. The installed library is the final `a55cssjit`, md5 `b5ba850f` |
| `/media/developer/temp/{wpe64,jsc64,jsc64own,jsc32}` | ~468 MB | 64-bit experiments |
| `/media/developer/bench/jetstream3.0` | ~466 MB | JetStream runs for WPE (`bench.py jetstream-js`) |
| `/media/developer/temp/{gdbtv,inspector,lsprobe,ndlprobe,wlglobals,wlshell_probe,…}`, the `com.viiees.ndlprobe` app | ~16 MB | Debugger, inspector resources, Wayland and NDL probes (`cr120/probe/*.c`) |

## Still present

| Where | Item | Why |
|---|---|---|
| Build host | Docker volume `cr151work`, image `cr151` | Active work |
| Build host | `cr120/content_shell.gz`, `cr120/cr120.tar.gz` | Last cr120 build, ready to deploy |
| Build host | `perf/bin/perf` | Static perf for the TV. Rebuilding it needs the deleted `wpe-br` toolchain |
| TV | `com.viiees.chromiumtv`, project Chromium TV, shown on the TV as "Chromium" (own build on WebOS-Chromium 1.1.1, tag `1b4d053`, reinstalled 2026-11-25 with the owner's yes with the launcher gpu.state change and TV Tools "GPU", IPK sha256 `b2ba8329â¦`, copy in `browser/build/ipk-1.1.1-gpustate/`; first 1.1.1 install that day IPK sha256 `6ad253c1â¦`, copy in `browser/build/ipk-1.1.1/`, our patches 0102â0104 and 0107 (0110 is their 0066); before that on 1.1.0, main `6071897`, installed 2026-11-23 with the owner's yes, IPK sha256 `d8b40da9…`; reinstalled 2026-11-25 with the owner's yes, IPK sha256 `ae1e0320…`, copy in `browser/build/ipk-chromiumtv-dark/`, adding `spotify.com` to TV Tools' default desktop sites and the dark theme (TV Tools "Dark theme", default On); before that, 2026-11-25, IPK sha256 `19c4b655…`, adding our autoconsent rule that hides Didomi consent-or-pay banners, + our patches 0102–0104, 0107 and 0110 + fonts.conf + omnibox trim and HistoryFuzzy + uBO Lite in complete mode, packed (`browser/extensions/ubol.crx`, id `bbdfhfkcgpkhdkbgpnelelegbhpimcek`) + DuckDuckGo autoconsent for cookie banners (lean-frames build) + `--disable-field-trial-config`, V8 `--sqrt-allocation-limits` and a TV Tools tab limit of 8 + TV Tools "Auto" resolution = 4K, (0107: closing the last tab opens a New Tab page; 0058 + 0109: no hang at exit, no omnibox slowdown), 265 MB, version 1.0.0, IPK sha256 259b879d…, reinstalled 2026-11-21 with 0109 and the packed uBO Lite, with the owner's yes; profile of `com.viiees.cr151p` moved in on 2026-11-18; the test web app Squoosh removed 2026-11-19 with the owner's yes, through chrome://apps) | The browser. TV Tools ships inside it (`ext/tvtools`). Rebuild: `cr151/package.sh` (its default id) |
| TV | removed 2026-11-25 with the owner's yes: `com.viiees.cr151p` ("Chromium test"), installed that day for the patch 0111 A/B (the owner asked for the tests): Chromium TV 1.1.0 + 0111, IPK sha256 `6f9a5fcd…`, copy in `browser/build/ipk-cr151p-0111/`. 0111 is shelved | Restore: `cr151/package.sh` with `CR151_APP_ID=com.viiees.cr151p` and the patch moved back to `patches/` |
| TV | removed 2026-11-21 with the owner's yes: `com.viiees.cr151p` ("Chromium bisect"), installed that day with the owner's yes for the omnibox bisect: Chromium TV 1.0.0 with 0109 (still numbered 0108 in that build), 246 MB, IPK sha256 88e9927d… (earlier removed 2026-11-18) | Restore: `cr151/package.sh` with `CR151_APP_ID=com.viiees.cr151p` |
| TV | removed 2026-11-18 with the owner's yes: `com.viiees.browser` (WPE), `com.viiees.cr120` + `/media/developer/temp/cr120`, `com.viiees.cr151`, `com.viiees.cr151b`, `org.nativechromium.browser` (0.0.66). About 1.3 GB | Restore: WPE from `buildroot/` (FROZEN, its STATUS.md), cr120 from `cr120/cr120.tar.gz` with `cr120/run_tv.sh`, cr151 variants with `cr151/package.sh` and `CR151_APP_ID`, 0.0.66 from the WebOS-Chromium release page or Homebrew Channel |
| TV | `/media/developer/temp/{evkeys,tcprelay,keepawake.sh}` (sources in `bench/`) | Benchmark tools |
| TV | removed 2026-11-25 with the owner's yes: `/media/developer/temp/acidle/autoconsent` (2026-11-22), the test copy of the lean-frames autoconsent with the idle wait. Chromium TV ships it now | Nothing to restore |
| Build host | `.adblock/` (official extension zips, adblock-rust clone). `cr151/package.sh` takes the uBO Lite zip and the autoconsent npm package (`autoconsent/autoconsent-18.9.0.tgz`) from here. `.adblock-build/` (extension copies, armv7 adblock-rust benches, build logs) was deleted 2026-11-19 with the owner's yes: the comparison is in ADBLOCK.md | uBO Lite for the package, adblock comparison |
| TV | `/media/developer/bench/{pages (incl. spatnav.html, fonts.html),media,speedometer3.1,motionmark1.3.2}`, `/media/developer/temp/{perf,threads*.sh}` | Benchmark set |
