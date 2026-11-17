# WebOS-Chromium 0.0.66 (Chromium 151) on the C1 — results 2026-11-17

Build under test: the release IPK `org.nativechromium.browser_0.0.66_arm.ipk` from
github.com/sarahahzub/WebOS-Chromium (108 491 662 bytes, sha256 9ffad27d…b34514, the digest GitHub and the release
notes publish). Chromium 151.0.7922.108, V8 15.1. Installed as a plain dev app with appInstallService/dev/install
(188 MB on /media/developer, no root scripts). Same TV, same day, same harness as cr120 and WPE.

## Safety check before install (12:20-12:40)

| Check | Result |
|---|---|
| IPK contents | Only `usr/palm/applications/<id>` and `usr/palm/packages/<id>/packageinfo.json`. control.tar.gz has no postinst/prerm. |
| `bin/run.sh` | Byte-identical to `source/package/run.sh` in the repo at tag 0.0.66. |
| `ext/tvtools` (TV Tools) | Identical to the repo except one comment line in bg.js. |
| `bin/run` (launcher, 53 KB) | Imports socket/bind/listen/accept4 only (AF_UNIX media socket), no connect, no getaddrinfo. Strings: luna-send toast, tvpower screensaver, NDL, EGL. Matches `cnrun.c`. |
| `browser/chrome` (154 MB) | strings: only stock Chromium hosts (Google, search engines, CA/OCSP, NEL beacons). No project-specific host, no update URL. |
| Auto-update | None in the app. Updates come from Homebrew Channel or a manual ares-install. |
| Ports | Before vs. after the first launch: no new LAN listener. `nc -z` from the Mac to 9222-9226 refused. DevTools is off unless `--remote-debugging-port` goes into `/tmp/<appid>/browser.flags`. With it, M151 binds 127.0.0.1 only (`--remote-debugging-address` is ignored); tests used a temporary tcprelay on :9226, removed after. |
| Launch parameters | run.sh takes `target` only when it starts with http:// or https://, so the cr120 argv-injection hole does not exist here. |

Not proven: that `chrome` was built from the published source. The source is complete (pinned chromium151 commit,
44 patches, build scripts), so a rebuild could verify it.
Structural risk (judgment): `--no-sandbox`, as in cr120. TV Tools runs a MAIN-world content script on every page.
It sets a webOS TV user agent and filters HLS/DASH manifests by a quality limit.

## Benchmarks (harness_run.py -b cr151,stock, 3 rounds; raw: harness_cr151.txt)

The stock browser ran interleaved as a control. Its numbers match the earlier runs (micro 334-355 ms, wiki
4.8-5.0 s), so today's TV state is comparable. cr120 and WPE come from their RESULTS files.

| Case | cr151 0.0.66 | cr120 (SW raster) | WPE 2.52.6 | Stock LG Chrome 87 (today) |
|---|---|---|---|---|
| micro | 340-345 ms | 259-309 ms | ~230 ms | 335-372 ms |
| load-wiki | 3.5-3.7 s (first, cold profile: 6.4 s) | 3.1-3.3 s | 2.9-3.0 s | 4.9-5.1 s |
| raf-wiki | 62.1-63.4 fps | 61.4 fps | 26-28 fps | 57.4-59.2 fps |
| raf-wiki-nojs | 62.3-64.4 fps | 62.8-63.1 fps | — | 63.6-64.4 fps |
| Speedometer 3.1 | 0.732-0.757 (2 runs) | 0.58-0.60 | 0.80-0.83 | does not start |
| YouTube home load (loadEventEnd) | 5.3-6.1 s warm cache, FCP 1.2-2.2 s; first two runs 10.1-10.5 s | 7.6-8.3 s | ~9.9 s | not measurable |

Notes:
- micro with `--js-flags` overridden (no `--optimize-for-size`): 332-357 ms, no change. The flag is not the cause
  of the slower micro. The other candidate (not tested): their size build (`optimize_for_size`, LTO without
  optimisation, no PGO).
- cr151 renders inside its own browser UI at device scale 1.5 (1280x720 DIP minus the toolbar); content_shell
  renders 1920x1080 at scale 1. Load and rAF numbers compare different viewports.
- YouTube: cdpnav.py over CDP. TV Tools sends a webOS TV user agent
  (`Web0S; Linux/SmartTV ... Chrome/151 ... WebAppManager`), cr120 sent Chrome 120's, so the payload may differ.
  No login. A third early run (16.0 s) ran under the screensaver and is dropped.

## Video (video_run.py cr151; raw: video_cr151.txt)

Caps: MSE yes. H.264, VP9, AV1, AAC, Opus yes. HEVC, VP9 profile 2, E-AC3 no. EME: ClearKey only.
CPU = jiffies over 8 s (800 = one core), sum of the top threads.

| Clip | Mode | cr151 | cr120 NDL (same code path) |
|---|---|---|---|
| h264+AAC 1080p30 | src | 14.8 s, 0/447 dropped, ~100 | 14.7 s, 0 dropped, ~56 |
| h264 1080p30 | src | 14.6 s, 0/443, ~60 | 14.8 s, 0 dropped |
| h264 1080p60 | src | 14.8 s, 0/895, ~85 | 14.8 s, 0 dropped |
| HEVC 2160p30 | src | NotSupportedError | not supported |
| VP9 1080p60 | src | 14.8 s, 0/897, ~95 | 14.8 s, 0/897 |
| VP9 2160p30 | src | 14.8 s, 0/450, ~80 | 14.9 s, 0/451 |
| AV1 1080p30 | src | 14.9 s, 0/450, ~60 | 14.9 s, 0/451 |
| h264 1080p30 frag | MSE | 15.0 s, 0/453, ~50 | 15.0 s, 0/453 |
| VP9 1080p60 | MSE | 15.0 s, 0/909, ~80 | 15.0 s, 0/910 |
| VP9 2160p30 | MSE | 15.0 s, 0/455, ~95 | 15.0 s, 0/455 |

The launcher threads `lxvideodec0:src` and `video-src:src` are LG's decoder pipeline, so all clips decode in
hardware. Results match cr120's NDL port, which came from this project. YouTube 4K60 was not watched on screen
today (owner not asked to look).

## GPU on the C1

On. The launcher's media.log: `gpu: on (EGL 1.4 driver, GPU probe passed)`. Mali Bifrost r9p0 has no
eglGetPlatformDisplay. eglGetPlatformDisplayEXT(WAYLAND) returns EGL_NO_DISPLAY, and eglGetDisplay(wl_display)
works (patch 0033). Chrome runs with `--enable-gpu-rasterization --in-process-gpu --use-cmd-decoder=validating`.
Images on en.wikipedia.org/wiki/Cat draw correctly (cap_wiki.png). cr120's GPU raster drew them as green boxes.
The probe result is cached per boot in /tmp; after a GPU crash the launcher turns the GPU off by itself (gpu.state).

## What they have that cr120 does not

- Full Chrome UI: tabs, omnibox, bookmarks bar, settings, extensions (cap_start.png, cap_wiki.png).
- LG remote and LG on-screen keyboard in Chrome's own UI (patches 0015-0017, 0043), Magic Remote pointer (0045),
  spatial navigation.
- TV Tools: per-site video quality limit, TV/desktop user agent switch, lite mode.
- Profile and cache on flash, a fresh start without restored tabs, memory caps (one renderer, 192 MB JS heap,
  MSE buffer limits), renice of non-media threads so LG's services stay responsive.
- Screensaver guard driven by the media session state (patch 0049).
- One build for webOS 4.4 and newer.
- Releases every 1-2 days (0.0.42 on 11-01 to 0.0.66 on 11-16), through Homebrew Channel.

They lack: DRM, HEVC (Chromium's mime check), a sandbox. DevTools needs a flag file and a relay.

## Verdict (judgment, from the numbers above)

1. **Use their build instead of cr120 as the Chromium browser.** It wins Speedometer (+25 %), YouTube load
   (-25 to -35 %), and has a working GPU raster on Mali, a real browser UI and remote support. Video is the same
   code. It loses micro (+11-33 %) and wiki load (+6-19 %). Memory was not measured (busybox ps has no rss column). WPE still leads JS (Speedometer 0.80, micro 230) but has
   no usable video and 26-28 fps rAF.
2. **Own 151 build with our changes: little to add.** GPU compositing, the screensaver guard and the launcher fixes
   from cr120 already exist in 0.0.66 (DevTools off, target checked). An own build is worth it only to check that the
   binary matches the source, or to try a speed build (no `optimize_for_size`, full ThinLTO) for the micro gap.
   Their build runs on a 64-CPU, 288 GB Modal machine. That is bigger than our colima.
3. cr120 then stays a fallback. Its own work items (GPU raster green images, a browser UI, remote input) are
   solved in 0.0.66.

## "Use system title bar and borders" (14:00, owner's question)

The setting exists in chrome://settings/appearance (pref `browser.custom_chrome_frame`, default true). Set to false
through `chrome.settingsPrivate.setPref`: no change live, and after a browser restart (pref saved as false) the
minimise / maximise / close buttons at the top right are still drawn. The setting does not remove them on webOS.
Set back to true. Screenshots: cap_titlebar_before.png, cap_titlebar_after.png, cap_titlebar_restart.png.

## TV state after the test

org.nativechromium.browser is installed (188 MB on /media/developer, 527 MB free before). Closed; no browser.flags,
no relay, no nosaver left running. Extra files: /media/developer/temp/threads_cr151.sh, /media/developer/temp/tcprelay.
The app's profile (on flash) holds cookies from youtube.com and wikipedia.org, no login.

## Own build (com.viiees.cr151), 2026-11-17

Source: WebOS-Chromium tag 0.0.66 (repo commit 1499d397, `upstream/COMMIT`), which pins webOS-ports/chromium151
0baacb2b. Their 42 patches unchanged, their args.gn plus `args.delta.gn`, their compat sysroot (glibc 2.24) and
public stub libraries, their launcher (cnrun.c, built with zig 0.13 as their step 6), run.sh, TV Tools and mkipk.py.
NSS/NSPR libraries are copied from their 0.0.66 IPK.

What we changed:

| Change | Where |
|---|---|
| `-O2` instead of `-Os`, ThinLTO with optimisation (`lto-O2` instead of `lto-O0`), ICF kept, no PGO | args.delta.gn |
| `-march=armv8.2-a -mtune=cortex-a55 -mfpu=neon-fp-armv8` (their effective flags: armv7-a, `-mfpu=neon`) | args.delta.gn, patch 0101 |
| Rust code for armv7, not the ARMv6 baseline that a non-armv7 `arm_arch` would select | patch 0101 |
| No minimise/maximise/close buttons in the tab strip on webOS | patch 0100 |
| App id `com.viiees.cr151`, title "Chromium 151 (own build)", next to theirs | package.sh |

Their patch 0012 adds `-mfpu=$arm_fpu`, but `compiler_arm_fpu` puts `-mfpu=neon` after it, so their build runs with
plain NEON. Patch 0101 sets the FPU in `compiler_arm_fpu` for arm_version 8.

Build host: colima aarch64 VM (12 cores, 24 GB), natively. Chromium 151 ships clang and Rust for x64 hosts only, so:
clang/lld 23.1.6 (apt.llvm.org), Rust nightly-2026-06-17 with prebuilt std for armv7-unknown-linux-gnueabi,
bindgen-cli, gn from source (`args.host.gn`, `Dockerfile`, `prep.sh`). arm32 V8 host tools run under qemu-arm with an
armel runtime (patch 0102). Steps: `incontainer.sh` sysroot, sysroot-compat, prep, builtins, patch, gen, build,
package. Traps on the way are in the project memory and FINDINGS.

Result: chrome 204 MB stripped (theirs 154 MB), IPK 136.5 MB, 233 MB installed. Their `check-abi.py`: 6 ELF files,
0 problems (glibc ≤ 2.24, loader /lib/ld-linux.so.3, no libwayland-egl by name).

### Our binary against theirs (compare.sh)

A different `-O`/`-march` cannot match byte for byte, so the comparison covers what a flag change leaves alone.

| Item | Ours | Theirs | Difference |
|---|---|---|---|
| NEEDED libraries | 23 | 23 | none |
| Exported dynamic symbols | 50 | 50 | none |
| URL hosts in strings | 748 | 748 | none |
| Version strings | 151.0.7922.108 | 151.0.7922.108 | none |
| Imported symbols | 1032 | 1072 | 46 only theirs, 6 only ours |
| .text | 170.8 MB | 120.4 MB | +42 % (-O2) |
| .rodata | 17.78 MB | 17.68 MB | +0.6 % |
| .data.rel.ro | 5.71 MB | 5.62 MB | +1.5 % |

The 46 imports only in theirs are libm/ctype calls that `-O2` and the ARMv8 FPU turn into instructions (rint, round,
sqrtf, fmax, isalpha, tolower...) and NSS calls LTO dropped. Judgment: their binary has the shape of a build from
the published source. Nothing in it (hosts, exports, libraries) is absent from ours. This is not a reproducible-build
proof: that needs a second build with their exact args, not done.

### Benchmarks: our build against theirs and cr120

Raw: harness_cr151own.txt (`harness_run.py -b cr151own,cr151`, interleaved, 3 rounds; Speedometer 2 rounds),
youtube_cr151own.txt (cdpnav.py over a temporary DevTools relay, removed after), video_cr151own.txt. The "theirs"
column is today's interleaved run, except YouTube and video (phase 1). cr120 numbers are from its RESULTS.

| Case | Our build | Their 0.0.66 | cr120 (SW raster) |
|---|---|---|---|
| micro | 306-370 ms | 346-434 ms | 259-309 ms |
| load-wiki | 2.72-3.14 s | 3.29-4.38 s | 3.1-3.3 s |
| raf-wiki | 62.9-63.5 fps (load 2.63-2.91 s) | 63.8-63.9 fps (load 3.48-3.71 s) | 61.4 fps |
| raf-wiki-nojs | 63.5-64.1 fps | 64.4-64.9 fps | 62.8-63.1 fps |
| Speedometer 3.1 | 0.825, 0.852 | 0.721, 0.744 | 0.58-0.60 |
| YouTube home, warm (loadEventEnd) | 5.4-6.3 s, FCP 1.4-2.3 s (cold 10.2-11.4 s) | 5.3-6.1 s | 7.6-8.3 s |
| Video (video_run.py) | NDL hardware, 0 dropped in all 9 playable clips, no HEVC; start 120-215 ms progressive | same, start 190-405 ms | same NDL path |

Screenshot without window buttons: cap_own_wiki.png (tab strip ends with the new-tab button, no minimise/maximise/close).

Launch checks: GPU probe passed (EGL 1.4 path, as theirs), NDL video works from our cnrun build, no new LAN listener
after launch (`nc -z` 9222-9226 refused), DevTools only with browser.flags, as theirs.

Verdict:
- Our build is faster where the CPU decides: Speedometer +14 % (now at WPE's 0.80-0.83), wiki load -20 to -30 %.
  micro is within noise of theirs and still behind cr120. rAF, YouTube and video do not change: they are bound by
  the GPU, the network or the hardware decoder.
- The cost is size: chrome 204 MB vs 154 MB stripped, 233 MB installed.
- Recommendation: use com.viiees.cr151 as the Chromium browser. Next speed step, not tried: PGO
  (`chrome_pgo_phase = 2` with Chromium's arm32 profile, if one exists for M151) and a second build with their exact
  args to settle the trust question byte for byte.
