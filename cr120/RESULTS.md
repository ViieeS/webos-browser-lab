# chromium120 (webOS OSE) content_shell on the C1 — results 2026-11-16

Build: browser/cr120 (args.gn, patches 0001-0011, extra/), non-official release (no PGO/LTO),
armv7 softfp, validating decoder on native Mali EGL/GLES, robustness extensions hidden.
Launch: run_tv.sh from telnet (no SAM app). Harness: bench/harness_run.py -b cr120, 3 rounds.

| Case | cr120 (3 rounds) | Our WPE 2.52.6 | Stock LG (Chromium 87) |
|---|---|---|---|
| micro | 270–295 ms | 232–264 ms | 334–355 ms |
| load-wiki | 3.6–4.7 s | 3.2–3.3 s | 4.8–5.0 s |
| raf-wiki | 59.7–60.3 fps | 10 fps | 59–60 fps |
| raf-wiki-nojs | 62.1–63.3 fps | 18 fps | — |
| Speedometer 3.1 | 0.606–0.613 | 0.744 | does not start |
| YouTube cold load (loadEventEnd) | 7.24–7.34 s, FCP 1.8 s | 10.1 s | not measurable |

Notes:
- Raw lines: harness_cr120.txt. Speedometer round 1 (0.602) ran under the TV screensaver; the
  range above is 2 rounds + 1 extra run with the saver blocked (nosaver.sh).
- YouTube: bench/cdpnav.py over DevTools :9224, same expression as navtime.py. Chrome 120 UA
  (WPE used a desktop Safari UA), so the payload may differ. Profile with consent rejected and
  a warm disk cache; the home feed is empty (no history), count of items = 0.
- Open issue: some content images render as a solid green box (GPU upload path on Mali), so
  raster/upload work may be under-counted.

## Green images fixed: software raster (2026-11-16 evening)
GPU raster draws content images as solid green boxes on Mali (not fixed by disabling JPEG/WebP
YUV decode or hiding GL_EXT/ARB_texture_rg). `--disable-gpu-rasterization` (CPU raster, GPU
compositing) draws them correctly and is now the default in run_tv.sh. Re-measure, 2 rounds
(harness_cr120_swraster.txt) + YouTube 2 runs:

| Case | cr120 SW raster | cr120 GPU raster (green images) |
|---|---|---|
| micro | 259–309 ms | 270–295 ms |
| load-wiki | 3.1–3.3 s | 3.6–4.7 s |
| raf-wiki | 61.4 fps | 59.7–60.3 fps |
| raf-wiki-nojs | 62.8–63.1 fps | 62.1–63.3 fps |
| Speedometer 3.1 | 0.581–0.596 | 0.606–0.613 |
| YouTube load | 7.6–8.3 s | 7.2–7.3 s |

## Video (2026-11-16 18:40, bench/video_run.py cr120, raw: video_cr120.txt)
Caps: MSE yes; h264, VP9, AV1, AAC, Opus yes; HEVC, VP9 profile 2, E-AC3 no; EME: ClearKey only
(no Widevine/PlayReady). All decoding is software in the content_shell process (FFmpeg for h264 on
"Media" threads, libvpx on ThreadPool workers, dav1d for AV1); no webOS media daemon gets any CPU
(use_neva_media=false). CPU = jiffies over 8 s of playback (800 = one core).

| Clip | played / 15 s | frames (dropped) | stalls | CPU, 8 s | WPE |
|---|---|---|---|---|---|
| h264 1080p30 | 14.4 s | 437 (3) | 2 | Media 1042 (1.3 cores) | ~14 fps |
| h264 1080p60 | 12.4 s | 750 (26) | 21 | Media 2537 (3.2 cores) | 48 frames in 14 s |
| HEVC 2160p30 | — | NotSupportedError | — | — | stalls |
| VP9 1080p60 | 10.6 s | 641 (49) | 31 | ThreadPool 2657 | — |
| VP9 2160p30 | 5.6 s | 174 (25) | 18 | ThreadPool 2855 | stalls |
| AV1 1080p30 | 14.2 s | 431 (1) | 2 | dav1d 1170 | not supported |
| h264 1080p30 MSE | 14.5 s | 438 (22) | 9 | Media 990 | — |
| VP9 1080p60 MSE | 10.9 s | 662 (52) | 32 | ThreadPool 2596 | — |
| VP9 2160p30 MSE | 6.1 s | 191 (25) | 19 | ThreadPool 3037 | — |

## Hardware video via webOS media (use_neva_media) — go/no-go, 2026-11-16 19:30
Probe without Chromium: ums_probe.sh loads a clip into com.webos.media (uMediaServer) over luna
from a telnet root shell, with option.appId = the foreground SAM app (stock browser launched for
the test). Resources from getActivePipelines, CPU = jiffies of starfish-media-pipeline in 10 s.

| Clip | State | HW resources | Pipeline CPU 10 s |
|---|---|---|---|
| h264 1080p30 | play | VDEC, G1_H264 | ~5 (0.5% of a core) |
| h264 1080p60 | play | VDEC, G1_H264 | 4 |
| HEVC 2160p30 | play | VDEC, HEVCP1_HEVC | 5 |
| VP9 1080p60 | play | VDEC, HEVCP1_VP9 | 125 |
| AV1 1080p30 | play | VDEC, HEVCP1_HEVC | 112 |
| VP9 2160p30 | error 600 "VDEC_BUS released by policy" | — | inconclusive: the screensaver pipeline (4K HEVC Aerial) held VDEC_BUS |

Video was not visible in these probes (windowId empty, behind the opaque browser window); the
compositor does advertise wl_webos_foreign 1, the protocol Chromium's foreign video window uses.

What OSE chromium120 neva media offers and what blocks it here:
1. Only URL playback (<video src>) goes to uMediaServer (MediaPlayerUMS / UMediaClientImpl). OSE has
   no platform MSE path, so MSE sites (YouTube, Netflix-style players) stay on software decode.
2. ABI: UMediaClientImpl derives from uMediaServer::uMediaClient in the TV's libumedia_api.so.1,
   built with libstdc++ (std::__cxx11::string in its methods); Chromium uses its own libc++.
   Needs a replacement client that speaks com.webos.media luna JSON (load/play/seek/subscribe),
   or a gcc-built bridge library with a C interface.
3. Gates: media/neva builds the webOS player only for is_webos && use_gst_media (pkg gmp-player-client,
   absent on the TV; the NDK gmp.pc is GNU MP). Needs local patches like 0002, and use_neva_media
   changes neva defines tree-wide -> full rebuild.
4. Policy: uMediaServer gives decoders to the foreground app's appId; content_shell is not a SAM app.
   The probes passed the foreground app's id; the screensaver (also a com.webos.media client) takes
   the decoders when it starts.
5. DRM: libplayreadycdm.so exports the Chrome library-CDM API (InitializeCdmModule_10,
   CreateCdmInstance), plausible for use_neva_cdm. libwidevine_ce_cdm_shared.so.16 is the Widevine
   CE CDM API, not loadable as a Chrome CDM.
Verdict: hardware decode is reachable (H.264 incl. 1080p60, HEVC 4K, VP9, AV1 on the TV's decoders),
but only for <video src> and only after new code (luna client + gate patches + full rebuild).
Not built yet.

## Hardware video, built (use_neva_media, 2026-11-16 22:40-23:05)

Built: args.gn use_neva_media=true, patch 0012 (webOS UMS player in media/neva) with
WebOSMediaClientLuna (extra/media/neva/webos/webos_mediaclient_luna.*: luna-send per call, one
`luna-send -i subscribe` per pipeline, appId com.webos.app.1), patch 0013 (get_position is webOS-only).

`video_run.py cr120` (CPU = jiffies in 8 s, 100 Hz, so 800 = one core):

| clip | mode | path | played in ~14 s | dropped | CPU 8 s |
|---|---|---|---|---|---|
| h264+AAC 1080p30 | src | uMediaServer, G1_H264 | 13.4 s | 0 | ~80 (starfish-media ~60, content_shell 12) |
| h264 1080p30, 1080p60, VP9 1080p60/2160p30, AV1 1080p30 (video-only) | src | uMediaServer | 0.2-0.5 s, then stalls | 0 | ~6 |
| HEVC 2160p30 | src | canPlayType "no", not loaded | 0 | - | - |
| h264 1080p30 frag | MSE | ffmpeg (software) | 14.6 s | 21/438 | ~1400 |
| VP9 1080p60 | MSE | libvpx (software) | 10.7 s | 56/641 | ~3700 |
| VP9 2160p30 | MSE | libvpx (software) | 6.1 s | 26/190 | ~3700 |

caps: drm_widevine=0, drm_playready=0, clearkey=1. src_hevc=no.

Findings:
1. <video src> with an audio track plays on the hardware decoder at ~10% of one core in total,
   against ~1.75 cores for software h264 through MSE.
2. uMediaServer stalls video-only clips after ~166 ms, also when loaded from luna-send directly:
   the pipeline clocks by audio (same as NDL). All bench clips were video-only; h264aac-1080p30.mp4
   (testsrc2 + 440 Hz AAC) was added. Fix candidates: a uMediaServer load option, or an MSE-like
   fallback to software for video-only files.
3. Visibility not verified: the capture service sees only the graphics plane (page shows a black
   box) and refuses VIDEO capture while a pipeline plays (REFUSED_PERMISSION_DENIED); before that
   the video plane was black. Needs a look at the screen.
4. MSE (YouTube) is still software: OSE has no platform MSE path.
5. Pipelines outlive a killed content_shell (luna-send clients); run_tv.sh now unloads them.
6. HEVC <video src> is rejected by Chromium's mime check before it reaches uMediaServer, though
   the TV decodes it (HEVCP1_HEVC in the luna probe).


## Hardware video through NDL, ported from WebOS-Chromium (2026-11-17 09:00-09:35)

content_shell now runs under dev app `com.viiees.cr120`: the app main is `launcher/cr120run` (SAM-launched ELF),
which owns LG's NDL DirectMedia (API 2) and starts content_shell as its child. The renderer sends demuxed video
(Annex B / raw VP9, AV1) and PCM audio over `/tmp/cr120/media.sock`; viz punches a transparent hole; the GPU process
exports the video window from the browser window surface and places the plane at the hole. Code: patches 0014
(viz hole, from their 0024/0026), 0015 (wiring), extra/content/renderer/media/cn_ndl_renderer.cc (their 0023,
adapted to 120), extra/ozone/wayland/foreign_window/cn_video_export.cc (new: their 0025 targets another ozone
backend). With NDL on, the launcher passes `--disable-web-media-player-neva`, so `<video src>` takes the same path.
Run: `video_run.py cr120app` (log video_ndl.log). Jiffies are per 8 s at 100 Hz (800 = one core).

| Clip | Mode | Before (2026-11-16) | NDL (2026-11-17) |
|---|---|---|---|
| h264+AAC 1080p30 | src | uMediaServer, 13.4 s | 14.7 s, 0 dropped, ~56 jiffies |
| h264 1080p30 / 1080p60 | src | stalled (video-only in UMS) | 14.8 s, 0 dropped, ~36-43 jiffies |
| HEVC 2160p30 | src | not supported | not supported (Chromium's mime check) |
| VP9 1080p60 | src | stalled | 14.8 s, 0/897 dropped, ~44 jiffies |
| VP9 2160p30 | src | stalled | 14.9 s, 0/451 dropped, ~37 jiffies |
| AV1 1080p30 | src | stalled | 14.9 s, 0/451 dropped, ~27 jiffies |
| h264 1080p30 frag | MSE | software, 14.6 s, 21/438 dropped, ~1400 | 15.0 s, 0/453 dropped, ~24 jiffies |
| VP9 1080p60 | MSE | software, 10.7 s, 56/641 dropped, ~3700 | 15.0 s, 0/910 dropped, ~28 jiffies |
| VP9 2160p30 | MSE | software, 6.1 s, 26/190 dropped, ~3700 | 15.0 s, 0/455 dropped, ~26 jiffies |

Findings:
1. NDL serves only the process SAM started from the appinfo "main" ELF: telnet root and a child of a shell main
   get exit() from smp::ResourceManager inside NDL_DirectMediaLoad (probe/ndlwin.c). Hence the launcher app.
2. MSE (YouTube's path) now decodes in hardware: CPU drops ~100x and nothing is dropped, up to VP9 4K.
3. Seen on the TV by the owner (09:45): picture in the page's video box, no black rectangle over it, AAC sound
   through the soundbar (ARC) once unmuted, in sync. content_shell's window was 800x600 (its default), stretched by
   LSM to the panel; the launcher now passes --content-shell-host-window-size=1920x1080: sharper text, no letterbox.
   The launcher also queues a stream that opens before the window's video id arrives (fast local pages lost it).
   Not checked yet: YouTube itself, HEVC (blocked before the renderer by
   Chromium's mime check), DRM (none, as before).
4. Bench tooling: run_tv.sh (telnet root) stays for non-video benchmarks; the NDL build needs the app.

### YouTube (2026-11-17 10:30-10:45, owner at the TV)

youtube.com/watch (Big Buck Bunny 4K60) in the cr120 app: MSE through NDL. The cookie banner pauses the player until
"Reject all". 720p AV1: 0 dropped, ~21% of a core (YouTube's JS). Quality switched to 2160p: the page builds a new
player, VP9 3840x2160 opens in NDL, ~60 fps, 0/2160 dropped, ~1.6 cores, all of it download/MSE append/JS, none
decode. Owner: smooth, with sound. The first 4K switch ended in YouTube's "Something went wrong" (stream flushed,
no new open); not reproduced on the second try with extra logging. Open: the clock screensaver came on during
playback (webOS does not know media plays; nosaver.sh saw no tvpower request).

### Screensaver during video (2026-11-17 11:40-12:00)

webOS does not know NDL video plays, so its idle screensaver came on ~1.5 min into YouTube. The launcher now holds it
off while frames flow: it registers with tvpower's registerScreenSaverRequest as `com.viiees.cr120.wakelock` and
answers each request with ack false; 3 s after the last frame it cancels and the TV's timer runs again. Requests
carry the timestamp as a quoted string and the answer must too (nosaver.sh parsed a number and never answered).
turnOnScreenSaver ignores the clients, so only the real idle timer tests this. Result: YouTube looped 4.5 min
without a key press, tvpower asked twice (every ~130 s), both answered "no", state stayed Active.
Also: on close, SAM killed a launcher whose YouTube content_shell outlived SIGTERM and the browser was orphaned;
content_shell now runs in its own process group, killed 2 s after a close. YouTube's cookie dialog pauses the
player, sometimes only after a few seconds.

### Launcher security fixes (2026-11-17 12:20-12:40, review by the peer session)

All in launcher/cr120run.c, no Chromium rebuild:
1. DevTools is off by default; a launch with `"devtools":true` in SAM's parameters turns it on (LAN IP only).
   video_run.py cr120app passes it. Checked: without it `nc -z $TV_HOST 9224` is refused.
2. `target` passes only http://, https:// and about: URLs, anything else becomes about:blank, and `--` goes before
   the URL (content_shell 120 honours it: https://example.com/ opened as a page). Checked: target
   `--renderer-cmd-prefix=/bin/true` was refused and logged, the page is about:blank, no such switch in any argv.
3. The OPEN message is memcpy'd into a local `struct cn_open` before use (it sits at odd offsets after odd-sized
   frames; uint64 loads there can SIGBUS on the A55 in compat mode).
Regression: video_run.py cr120app same as before (all but HEVC, 0 dropped); YouTube 4K VP9 through NDL, 0 dropped.
