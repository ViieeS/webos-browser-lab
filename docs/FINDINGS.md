# Findings: a modern web browser on the LG OLED C1

Knowledge base for building a fast, modern web browser for a rooted LG OLED C1 (OLED55C1RLA, webOS TV 6.5.3, see [SOURCES.md](SOURCES.md)).
It collects platform facts, measurements, patches and dead ends from 2026-10-27 to 2026-11-17.
Read it before you start, so you do not repeat work that already failed.

Conventions:

- `$TV_HOST` is the TV's LAN address. Replace it with your own.
- CPU numbers in "jiffies" are per 8 s at 100 Hz. 800 jiffies = one full core.
- "micro" is `browser/host/bench.html` / `bench.js` (int loop, math, objects, strings, DOM).
- Run-to-run noise on the TV is large. Repeat a measurement before you trust a delta under about 1.5x.

## Status at a glance

| Track | Directory | Status | Why |
|---|---|---|---|
| WPE WebKit 2.52.6, 32-bit | `browser/buildroot`, `browser/host` | Frozen | Best JS score, but software video only and weak scrolling |
| 64-bit path (aarch64 jsc, bridge) | `browser/buildroot64`, `browser/bridge64` | Frozen | ~1.6x JS, but display and media stack are 32-bit only |
| Chromium 120 from webOS OSE | `browser/cr120` | Frozen, fallback | Built from verified sources, NDL hardware video works |
| WebOS-Chromium 151 | `browser/cr151` | Active direction | Faster, working GPU raster, full browser UI, same NDL video |

## Prior art

- System web engine on webOS 6.0 is Chromium 79 (signageOS table). webOS 22 uses 87. The stock browser on the C1 reports Chrome/87.0.3945.79 (see section 5). All web apps use the system engine. It cannot be replaced without firmware.
- Cobalt (YouTube) implements a subset of HTML/CSS/Web APIs for full-screen D-pad apps. It cannot open arbitrary sites.
- Browser shells over the system WAM exist: [atlet99/astra-webos-browser](https://github.com/atlet99/astra-webos-browser) (reuses the TV's Chromium 120 on webOS 25) and [jsong1230/webosbrowser](https://github.com/jsong1230/webosbrowser) (Enact PoC, cannot load external sites). On a C1 such a shell gets the system engine.
- [kimjione1206/tv-wpe-build](https://github.com/kimjione1206/tv-wpe-build): buildroot-nc4 `webos_tv_defconfig` plus `wpe.fragment`. CI green since 2026-10-20. Pins [openlgtv/buildroot-nc4](https://github.com/openlgtv/buildroot-nc4) @322ff04 (wpewebkit 2.50.5, wpebackend-fdo 1.16.1, cog 0.18.5). About 58 min on GitHub Actions. JIT off (CLoop), no multimedia (`BR2_PACKAGE_WPEWEBKIT_MULTIMEDIA` unset), cog headless only because there is no xdg-shell. Its patches seeded our WPE 0001-0004 and the libgcrypt and memfd patches.
- [webosbrew/webos-bridge-64to32](https://github.com/webosbrew/webos-bridge-64to32) issue #1 (2026-10-28, OLED65C1, webOS 6.4): WPE 2.54.2 arm64 from Debian sid through the GL bridge, 55-58 fps with single-threaded painting plus multi-threaded GPU compositing, after 12 bridge patches attached to the issue. Multi-threaded Skia GPU painting gives a black window. The reporter says `wl_shm` buffer attach "does nothing" through the bridge (natively unverified). No maintainer reply as of 2026-11-09.
- [sarahahzub/WebOS-Chromium](https://github.com/sarahahzub/WebOS-Chromium) (BSD-3, source in `source/`): Chromium 151 from [webOS-ports/chromium151](https://github.com/webOS-ports/chromium151) (LuneOS, derived from OSE chromium120). armv7 softfp, `is_webos=true`, EGL/GLES2 without ANGLE, `--no-sandbox`, NDL video for every `<video>`. Releases 0.0.42 (2026-11-01, webOS 9+ only, glibc 2.35) to 0.0.65 (2026-11-15, webOS 4.4+) and 0.0.66 (2026-11-16). Issue #2 reports a C1 on webOS 6.5.3 working. The fork danzig666/WebOS-Chromium is the same project.
- pecrow/WebOS-Brave-Browser-Port: Brave on Chromium 155, LG B9 (webOS 4.10), root, software rendering, a native helper decodes H.264/AAC in hardware.
- [webosbrew/apps-repo#252](https://github.com/webosbrew/apps-repo/issues/252) is the umbrella request for a Chromium port.
- Media references: [xbmc/xbmc](https://github.com/xbmc/xbmc) `MediaPipelineWebOS.cpp` (GPL), [GLinnik21/plx-native](https://github.com/GLinnik21/plx-native) `src/starfish.c` and `docs/` (GPL-3, seek workarounds per webOS version), [mariotaku/ss4s](https://github.com/mariotaku/ss4s) `modules/webos/ndl/webos5` and `modules/webos/smp`, [webosose/chromium84](https://github.com/webosose/chromium84) `media/neva/webos/media_platform_api_webos_smp` (Chromium MSE on SMP). The project allows reuse of GPL code from Kodi and plx-native. GPL obligations apply on distribution.

## 1. Hardware and platform facts

### SoC, kernel, memory

- CPU: 4x Cortex-A55 (CPU part 0xd05). perf reports cycles at 1.686 GHz.
- Kernel: aarch64, Linux 4.4.84 (`uname -m` = aarch64). Userspace is 32-bit armv7 softfp.
- No `/lib64`, no aarch64 loader on the TV.
- glibc 2.28, loader `/lib/ld-linux.so.3`. No `ld-linux-armhf.so.3`.
- Total RAM about 2.6 GB. 1.2 GB of it is CMA (video). zram swap, swappiness 100.
- No cpufreq in sysfs. Frequency is not managed by Linux.
- Load average about 13 at idle. It comes from LG driver kthreads in D state, not from real load.
- `/tmp` is tmpfs and is wiped on reboot.
- `/media/developer` (= `/mnt/lg/appstore`) is the persistent 2.7 GB partition for dev apps.
- Software ABI: libplayerAPIs, SDL and EGL are softfp. Cobalt reports `floating_point_abi softfp`.
- 128-bit aligned NEON stores (`vst1.8 {d16-d17}, [rN :128]`) on an 8-aligned address raise SIGBUS. 64-bit loads at odd offsets can also SIGBUS in compat mode. See WPE patch 0013 and the cr120 launcher fix.

### Wayland compositor (surface-manager / LSM)

Probed 2026-11-09 with a 32-bit native wayland/EGL probe:

- Globals: `wl_compositor` v3, `wl_shm`, `wl_shell` v1, `wl_webos_shell`, `wl_seat` x4, `wl_output` v2, `wl_mali`, `wl_starfish_*`, `wl_webos_foreign` 1.
- Missing: `xdg_wm_base`, `wl_subcompositor`, `linux-dmabuf`.
- Socket: `XDG_RUNTIME_DIR=/tmp/xdg`, `WAYLAND_DISPLAY=wayland-0`, owned root:composit 0660.
- libwayland-client on the TV is 1.11. The NDK says so too. The TV links libffi.so.6, the NDK copy wants libffi.so.8.
- A plain `wl_shell` toplevel renders (about 55 fps of EGL clears) but is NOT shown on screen (2026-11-16).
- A `wl_shell` surface plus `wl_webos_shell_get_shell_surface` with property `appId`, `_WEBOS_WINDOW_TYPE_CARD` and state FULLSCREEN IS shown. The compositor sends state 3 and exposed. No SAM launch is needed for that.
- LSM hides a hardware video plane under a surface region declared opaque. Send no opaque region when video is behind the page.
- `eglSwapBuffers` does not pace to vsync, the same as native SDL.

### EGL and Mali

- Mali-G51, kernel driver mali_kbase r9p0-01rel0 (UK 11.0), `/dev/mali0`.
- EGL 1.4 (ARM Bifrost r9p0). It has `EGL_WL_bind_wayland_display`, `surfaceless_context`, fence/wait_sync, `KHR_image`.
- No `EGL_KHR/EXT_platform_wayland` (only `platform_base`). No `dma_buf_import`.
- No `eglGetPlatformDisplay`. `eglGetPlatformDisplayEXT(WAYLAND)` returns `EGL_NO_DISPLAY`. `eglGetDisplay(wl_display)` works.
- GLES 3.2 with `OES_EGL_image_external`. Has `glGetMultisamplefv` and `glGetTexLevelParameteriv`, which Skia needs for a GPU context.
- Mali reports `GL_ALPHA_BITS` 0 like PowerVR. Request RGBA explicitly when you need alpha.
- Only 32-bit libmali/EGL/GLES exist. The Xilinx r9p0 aarch64 libMali is Utgard (Mali-400) and does not fit.
- Mali's `libwayland-egl.so.0` is the vendor library. Do not shadow it with buildroot's `libwayland-egl.so`, or `eglCreateWindowSurface` fails with `EGL_BAD_ALLOC`. Software that needs `.so.1` gets a symlink to `/usr/lib/libwayland-egl.so.0`.
- Toolchain gcc needs an explicit `--sysroot=<toolchain>/arm-webos-linux-gnueabi/sysroot`, or it does not find the EGL headers.

### SAM, LS2 and the app jail

- A SAM-launched native app runs jailed as uid 6057. Its `/tmp` is `/var/palm/jail/<appid>/tmp`.
- SAM passes its JSON launch parameters as `argv[1]` to a native main. stdout goes nowhere. Redirect it to a file when `$APPID` is set.
- SAM's `LD_LIBRARY_PATH` puts the app lib dir LAST, so the TV's own glib and GStreamer 1.16 win. Bundled libraries need `DT_RPATH` (`-Wl,--disable-new-dtags`, which outranks `LD_LIBRARY_PATH`) on every executable.
- Running an app binary from telnet fails with "No available video device" and "APPID not set".
- ls-hubd checks the executable path. `LSRegister("com.webos.media.client-…")` and anonymous `LSRegister(NULL)` from a telnet-root binary both fail with "Invalid permissions" (2026-11-16). `/usr/bin/luna-send` is trusted.
- The app's main ELF may `LSRegister(NULL)` inside the jail (verified 2026-11-17).
- A `run.sh` wrapper as appinfo `main` makes LS2 refuse `com.webos.rm.client.*` ("Invalid permissions", `LSRegisterPubPriv FAILED`).
- Dead end: wrapping or copying the stock browser binary fails with `LUNASERVICE ERROR -1027: Invalid permissions` from ls-hubd. A bind mount over the host path is ignored. Only a bind over the jail path (`/var/palm/jail/com.webos.app.browser/media/system/apps/.../chrome`) is what the app executes. Its flags are compiled into `libcbe.so` (103 MB, no flags file, the launcher only takes `--webos-launch-json=`), so DevTools on the stock browser needs a binary patch of `libcbe.so`. All mounts were removed.
- Back key: call `SDL_SetHint(SDL_HINT_WEBOS_ACCESS_POLICY_KEYS_BACK, "true")` before `SDL_Init`. Without it webOS keeps Back and asks "close the app?".
- SAM relaunches an app killed under memory pressure (see below) with `{"reason":"autoReload"}` and without the original parameters.
- On close SAM kills the app main. A child that outlives SIGTERM is orphaned. Put children in their own process group and kill the group 2 s after close.

### App environment variables that break a bundled stack

- `GIO_EXTRA_MODULES=/usr/lib/gio/modules` loads gnutls from glib-networking 2.54, incompatible with a newer glib. Unset it and set `GIO_USE_TLS=openssl`.
- `GST_PLUGIN_PATH_1_0`, `GST_REGISTRY_1_0`, `GST_REGISTRY_UPDATE=no` and `GST_PLUGIN_SCANNER_1_0` point at LG's plugins. Versioned variables win over plain ones. LG plugins then load into a bundled GStreamer and the type system breaks ("cannot register existing type GstVideoScale"), which hung YouTube. Unset all of them in-process, set the `_1_0` variants yourself, point `GST_PLUGIN_SYSTEM_PATH` at bundled plugins and set `GST_REGISTRY_FORK=no`.
- `/etc/fonts` has only `conf.d/31-webos-aliases.conf`. There are no generic aliases, so "serif" matches nothing. Ship your own `fonts.conf` (generic and web font aliases to Tinos, Droid and LG Smart UI, `append_last` fallback, reject `*.bin`) and set `FONTCONFIG_FILE`.

### Memory-pressure kills

- Pattern (2026-11-11): kernel "MemNotifier drop_caches: 3", memchute logs `NL_MM_PROCLIST`, the window goes invisible, SAM logs `NL_APP_LAUNCH_BEGIN <appid> caller=com.webos.surfacemanager mode=autoReload`. surface-manager itself does not restart.
- It looks exactly like a manual relaunch from the remote. Check the logs before blaming a human.
- Logs: `/tmp/var/log/messages.N.gz` (SAM, LSM, memchute), `legacy-log` (kernel), `bootd.log` ("Respawn) foregroundAppId").
- After boot the system browser `com.webos.app.browser` (uid 5628) can sit at about 240% CPU with YouTube preloaded, leaving about 190 MB free. Close it and YouTube before any measurement. That frees about 140 MB.

### Screensaver

- webOS does not know that NDL or custom video plays. The idle screensaver comes on about 1.5 min into playback.
- tvpower asks `registerScreenSaverRequest` clients every ~130 s of idle.
- The request carries `"timestamp"` as a quoted string. `responseScreenSaverRequest` accepts it only quoted. A number gives `errorCode -12`.
- Dead end: an early `nosaver.sh` parsed the timestamp as a number and never answered, so it never blocked the saver.
- `turnOnScreenSaver` ignores registered clients (forced). It cannot test a guard. Only the real idle timer does.
- Working guard (2026-11-17): the app main registers as `<appId>.wakelock` while frames flow and answers `ack: false`. It cancels 3 s after the last frame. It kept the TV Active through 4.5 min of YouTube.
- Launching a SAM app dismisses the saver. `luna://com.webos.media/closeByAppId` with `com.webos.app.screensaver` stops its pipeline.
- The saver (Aerial 4K HEVC) is itself a `com.webos.media` client. It holds `HEVCP1_HEVC`, `VDEC` and `MAIN_SCALER`. Close it before any media probe.

### Resource manager, NDL, uMediaServer

- Libraries: `libNDL*`, `libumedia_api`, `libumedia_api_c.so.1`, `libresource_mgr*`, `libplayerAPIs.so.1`, `libwayland-starfish-client`.
- System GStreamer 1.16.2 with `gst-inspect-1.0` and `gst-launch-1.0` in `/usr/bin`. The toolchain sysroot has 1.20.
- LG elements: `lxvideodec` (H.264, HEVC, VP9, AV1, VP8, MPEG, output I420) and `lxvideosink` ("LG BSP Video Sink", `resource-info` property for core-type and ports). Also `omx_*`, a Dolby Vision bin, `lxaudiodec` (AAC, AC3, AC4, Opus, Vorbis, FLAC) and `lxaudiosink`.
- Also `cencdrmwidevine`, `playready`, `dashdemux`, `hls`, `adaptivedecryptor`. The CDM inside them is bound to LG apps.
- `/dev/video10` exists but is root-only (crw-------).
- Decoder resource names seen: `VDEC`, `VDEC_BUS`, `G1_H264`, `HEVCP1_HEVC`, `HEVCP1_VP9`, `ADEC`, `MAIN_SCALER`.
- Error 601 "Resource Allocation Error". Error 600 "VDEC_BUS released by policy".
- `luna://com.webos.media/getActivePipelines` lists who holds what. Check it before you trust a probe.
- 4K60 H.264 does not exist on this SoC (plx-native `docs/webos10-resource-allocation.md`).
- Video goes to a hardware plane. The page must punch a transparent hole.

### DRM libraries

- `libplayreadycdm.so` exports the Chrome library-CDM C API (`InitializeCdmModule_10`, `CreateCdmInstance`, `GetCdmVersion`). OSE's neva CDM looks for `InitializeCdmModule`. Plausible, untested.
- `libwidevine_ce_cdm_shared.so.16` is the Widevine CE CDM (`widevine::Cdm::create`), not the Chrome CDM API. It needs a shim. Untested.
- The homebrew "YouTube webOS Cobalt AdFree" 1.2.5 (a repackaged build of LG's Cobalt 23.lts, `eg_gold`, soc `lm21u`) calls StarfishMediaAPIs directly plus `wvcdm` for Widevine.

### Runtime libraries Chromium `is_webos` code expects

Present on the TV: `libluna-service2.so.3` (3.21.2), `libPmLogLib.so.3`, `libwebosi18n.so.1`, `libpbnjson_c/cpp.so.2`, `libwayland-webos-client.so.1`, libxkbcommon, `libnss3`/`libnspr4`, ICU 62, glib 2.58.

### Input

- Keep the TV's own libxkbcommon. A newer one rejects LG keycodes above 0xfff.
- SDL ABI trap: buildroot-nc4's SDL2 headers (patch `001-webos-input-structs`) always add `Uint32 inputSource` to key, text-editing and text-input events. SDL2-webOS from sdlpkg adds it only under `SDL_WEBOS_BROKEN_ABI`. Mixing them shifts every field by 4 bytes. Compile against `sdlpkg/include/SDL2`.
- buildroot-nc4's SDL2 has no Wayland driver (`BR2_PACKAGE_SDL2_WAYLAND` unset). Use sdlpkg's SDL2-webOS 2.30.12.
- The system SDL 2.0.10 `SDL_CreateRenderer` killed the process in the NDL test. Draw with GL instead.

### Tooling on the TV

- BusyBox 1.29.3. `nc` has no `-l`. `ps` has no rss column. curl and wget exist. SSH on port 22 was not checked.
- perf: static build from linux-4.4.302 `tools/perf` with the 32-bit toolchain (`browser/perf/build_perf.sh`). Flags `NO_LIBELF` etc., `-Wno-implicit-int -std=gnu11 -fcommon`, strip `@GLIBC` versions from `libtraceevent-dynamic-list` between two links. `armv8_pmuv3` counters work, `perf_event_paranoid=1`. `browser/perf/perfsym.py` records a process and symbolizes with addr2line. perf has no inspector distortion.
- gdb 16.3 with its libs under `/media/developer/temp/gdbtv`, run with `LD_LIBRARY_PATH`. Attach takes more than 3 s. Symbols need the unstripped library installed.
- Dead end: gdb breakpoints inside libWPEWebKit never fired, not even on `performLayout` during scroll. Thumb mode is suspected, not resolved. Use env-gated debug prints instead.
- gdb cannot unwind through the TV's libc. Workaround: dump the stack (`x/3000xw $sp`), keep odd words inside the library mapping (Thumb return addresses), `addr2line` at `addr - base - 1`. Copies of the TV's libc, ld and libpthread help: fetch them with `host/tvfetch.py` (not versioned). Script: `browser/host/corestack.py`.
- gdb often reports an idle futex thread as current in a core. Find the faulting thread yourself.
- Core files land in the app's cwd. Crashing web processes left 300-580 MB cores that filled `/media/developer` to 100%.
- Screen capture as root: `luna-send -n 1 luna://com.webos.service.capture/executeOneShot '{"path":"/tmp/x.png","method":"DISPLAY","format":"PNG","width":480,"height":270}'`. It captures the graphics plane only. `"method":"VIDEO"` is refused (`REFUSED_PERMISSION_DENIED`) while a pipeline plays.
- `/usr/sbin/lighttpd` serves local benchmarks (`browser/bench/lighttpd.conf`, 127.0.0.1:8099, root `/media/developer/bench`). Start it after every reboot.
- Disk cleanup (2026-11-11): store-demo videos (`preload/storedemo/*.lge`, 1.4 GB), `preload/igallery/21y_igallery_02.squashfs` (223 MB) and `preload/storeusp/usp_03.squashfs` (126 MB) were removed. The squashfs files are loop-mounted at boot, so unmount first. Restoring them needs a firmware reflash.

## 2. Video on webOS

Hardware paths are below. NDL and uMediaServer clock video by audio and stall on video-only streams. SMP plays video-only with `needAudio:false`.

| Path | Entry | Who may use it | Controls | Result on the C1 |
|---|---|---|---|---|
| NDL DirectMedia v2 | `libNDL_directmedia.so.1`, headers `usr/include/libndl-media` | Only the SAM-launched appinfo `main` ELF | Play, Flush, SetArea. No pause, seek or current time | Works. Used by cr120 and WebOS-Chromium |
| StarfishMediaAPIs (SMP) | `libplayerAPIs`, header `usr/include/starfish-media-pipeline` | SAM app | Load, Feed, Play, Pause, Seek, getCurrentPlaytime, SetPlayRate, pushEOS, flush, setHdrInfo, setVolume, setWindowId | Works in a test app incl. 4K HEVC. Not wired into a browser |
| uMediaServer (`com.webos.media`) | luna JSON or `libumedia_api` | Trusted client, decoders go to the foreground appId | load, play, seek, subscribe, unload | Works for URL playback. Stalls without audio |
| Raw GStreamer `lxvideodec` | system GStreamer 1.16.2 | root | — | Decodes, but no usable output |

### Raw GStreamer (dead end)

- 2026-11-09: `lxvideodec` decodes H.264 1080p (300 frames in 2.8 s) and VP9 to fakesink from a root shell.
- Its output buffers are 204-byte handles, not pixels. A CPU or GL path cannot read the frames.
- `lxvideodec ! lxvideosink` prerolls and then hangs in PLAYING, because no video output is connected.
- WebKit 2.50 needs GStreamer >= 1.18.4. Loading the LG 1.16 plugins into it breaks the type system.

### NDL DirectMedia

- 2026-11-09: 600 H.264 1080p frames over 20 s, 0 play errors. Resource manager acquires VDEC and MAIN. NDL uses GStreamer internally.
- 2026-11-10: picture confirmed on screen.
- NDL v2 is a thin wrapper over StarfishMediaAPIs.
- API sequence (from ss4s, used by moonlight-tv and chiaki-lg): `NDL_DirectMediaInit(getenv("APPID"))` once, `NDL_DirectMediaLoad(&info, cb)`, `NDL_DirectVideoPlay(buf, size, pts_ms)`, reload on size or aspect change, `NDL_DirectMediaUnload`. One media at a time.
- PTS is in ms since load. Video renders on arrival (low latency).
- Codecs: video H.264, H.265, VP9, AV1. Audio PCM, MP3, Opus.
- Order that works (2026-11-17): export a VIDEO element from the app's own toplevel surface, `set_exported_window` full screen, `set_property` mute off, `SetWindowId`, `Init(appId)`, `Load`.
- Requirements, each learned by a failure:
  - `Init` succeeds from anywhere. `Load` constructs `smp::ResourceManager` (libplayerAPIs), which calls `exit()` unless the process executable is the appinfo `main` ELF started by SAM.
  - A shell `main` that `exec`s the binary still gets `exit()`. Telnet root gets `exit()` too. Find such silent exits with an `atexit` hook plus `backtrace_symbols_fd`.
  - SDL video must be initialised with a mapped window. Without it: "fail creating exported window: no video device" and exit.
  - Keep the window transparent, cleared with GL to RGBA(0,0,0,0) every frame.
  - Always feed audio. Video with no audio showed the first frame and froze. Silent PCM (1600 stereo S16 frames per 1/30 s, same ms PTS) made it play.
  - SDL2 "Video subsystem has not been initialized" errors from `SetWindowId`/`Init` are harmless.
- Logs: define and export (`-rdynamic`) `_PmLogMsgKV` and `PmLogString_` in the binary to see NDL and player logs (from punktfunk/client-webos `docs/NOTES.md`).
- Probe 2026-11-17 (`browser/cr120/probe/ndlwin.c`, dev app `com.viiees.ndlprobe`): Load = 0, uMediaServer allocates VDEC + G1_H264 + ADEC + MAIN_SCALER, 300 Annex-B frames at 30 fps (split at AUD), 0 failures, about 6% of one core. Callbacks 22, 26, 23, as in WebOS-Chromium issue #2.
- Correction: on 2026-11-10 NDL was judged the wrong API for browser video, because v2 has no pause, seek or clock. On 2026-11-17 the NDL port from WebOS-Chromium made it the working path for `<video src>` and MSE up to VP9 4K, including YouTube. The browser keeps its own clock above NDL. Seek and pause through NDL are not verified in depth.

### StarfishMediaAPIs buffer feed

Tested 2026-11-10 with a standalone test app (its source was not kept, clips in `/media/developer/temp`):

- H.264 1080p, HEVC 4K 10-bit, VP9 4K, AV1 4K: Load, Play, Pause, Play and Seek back all work. Smooth 4K HEVC, VP9 and AV1 confirmed on screen. The freeze at clip end is the expected hold on the last frame.
- The shown PTS follows the feeder clock about 300 ms behind.
- Construct `StarfishMediaAPIs()` with NO uid. With uid = appId the resource manager refuses VDEC (601) even when nothing holds a decoder.
- Always set `option.adaptiveStreaming {maxWidth, maxHeight, maxFrameRate}` to the stream's real class. Without it SMP requests VDEC qty 4.
- `getCurrentPlaytime()` stays 0 in BUFFERSTREAM mode. Callback type 0 = frame shown, `num` = its PTS in ns, sampled about every 6th frame. Keep your own media clock.
- Kodi's Load payload works with `needAudio:false`.
- Feed JSON: `{"bufferAddr":"0x..","bufferSize":n,"pts":ns,"esData":1}` (1 video, 2 audio). Reply contains Ok, BufferFull or Error.
- `Seek("ms")` works without an extra flush. Feed from a keyframe after it.
- Event codes: 4 video info, 23 unload done, 25 seek done, 26 playing, 27 paused.
- `Feed` is a cxx11-ABI symbol. webOS 3.x lacks it.
- Build: `g++ -static-libstdc++ -rdynamic -lplayerAPIs -lSDL2 -lGLESv2 -I sysroot/usr/include/starfish-media-pipeline`. Window: `SDL_webOSCreateExportedWindow(0)` plus `SDL_webOSSetExportedWindow(id, src, dst)`, id goes in `option.windowId`.
- SMP is the better base for a WebKit MSE backend. It is not wired into any engine yet.

### uMediaServer (`com.webos.media`)

- A root telnet client can load: `luna-send -n 1 luna://com.webos.media/load '{"uri":"file:///...mp4","type":"media","payload":{"option":{"appId":"<foreground appId>","windowId":""}}}'`, then `/play`, `/subscribe`, `/seek`, `/unload`.
- Decoders go only to the foreground app's appId. A non-foreground appId gets 601 or never starts.
- Caveat: an early "video on screen at 0.12 core" reading was most likely the screensaver's own pipeline. Check `getActivePipelines`.
- Probe 2026-11-16 (stock browser foreground): h264 1080p30/60 on VDEC + G1_H264, HEVC 4K on HEVCP1_HEVC, VP9 1080p60 on HEVCP1_VP9, AV1 1080p on HEVCP1_HEVC. Pipeline CPU 0-1.5% of a core. VP9 4K got 600 "VDEC_BUS released by policy" while the screensaver pipeline existed.
- A clip with no audio track stalls after about 166 ms (from luna-send and from the browser). The same clip with AAC plays.
- `notifyForeground` is not a method on webOS 6 (error -1). Harmless.
- Pipelines of a luna-send client outlive the client process. Unload them on start and stop.

### What is still missing

- DRM: no Widevine and no PlayReady in any engine. cr120 and cr151 offer ClearKey only. WPE has no EME at all.
- HEVC: Chromium's mime check rejects it before it reaches the renderer, though the TV decodes it.
- HDR, Dolby Vision: not attempted.
- Video plane visibility cannot be checked by screen capture. A human must look.

- uMediaServer video was never confirmed on screen: luna capture sees only the graphics plane. Only the NDL path was checked by eye (2026-11-17).
- The cr120 uMediaServer client spawns `luna-send` instead of linking luna-service2. Without system role files (deliberately left untouched) `base::LunaServiceClient` cannot register from content_shell.

## 3. WPE WebKit 2.52.6 (frozen)

Design: native 32-bit WPE, own SDL host window (`browser/host/main.c`). The host takes frames from wpebackend-fdo exportable EGL as EGLImages (`EGL_WL_bind_wayland_display`). This avoids xdg-shell and dmabuf. App id `com.viiees.browser`. Host log: `/var/palm/jail/com.viiees.browser/tmp/browser.log`.

### Build

- `browser/buildroot/build.sh`, Docker volume `wpe-br`, colima VM 8 CPU / 20 GB. buildroot-nc4 builds host-gcc 16.2 and host-gdb. The first pass took about 1.5 h to reach gstreamer.
- Toolchains: the NDK (`toolchain/arm-webos-linux-gnueabi_sdk-buildroot`) has GCC 12.2 armv7 gnueabi with wayland-client/egl, EGL, GLESv2 and GStreamer 1.20. buildroot-nc4 builds WebKit with gcc 16.2. Target glibc 2.12.2 is older than the TV's 2.28, so binaries run against the TV's libc and no libc needs bundling.
- buildroot-nc4 defconfig: `BR2_GCC_TARGET_CPU="cortex-a9"`, neon-fp16, softfp, thumb, `-Os`.
- WebCore unified sources: 8295 ninja steps, about 8 steps/min. 6 jobs used about 10 of 20 GB. -O2 with 8 jobs hit OOM at step 4117 (cc1plus killed). Cross-compiling other work on a 32 GB Mac at the same time can also kill cc1plus. Retry with -O1.
- `wpe.fragment` says `BR2_JLEVEL=8`, but an existing volume's `.config` keeps its old value.
- Resume after a failure with `build.sh all` without dirclean. ninja keeps objects.
- `build.sh "<pkg>-dirclean all"` re-runs a package. A bare `docker run` fails because `BR2_GLOBAL_PATCH_DIR=/src/patches` is mounted only by build.sh.
- Hand edits in `output/build/wpewebkit-*/` are not recompiled by `build.sh all` (stamp exists). Use `build.sh wpewebkit-rebuild all`.
- `WEBKIT_MCPU=cortex-a55 build.sh wpewebkit-reconfigure all` rebuilds WebKit only with `-mcpu=cortex-a55`. buildroot's `toolchainfile.cmake` ignores `BR2_TARGET_OPTIMIZATION` once the toolchain exists. CMakeCache keeps `CMAKE_C/CXX_FLAGS` from an earlier `-D`, so switching needs reconfigure with an explicit value, never an empty one. Without `WEBKIT_MCPU` the next run reverts to cortex-a9.
- gst1-plugins-bad 1.24 fails at configure: `gst-libs/wayland` needs wayland-client >= 1.15, buildroot-nc4 has webOS's 1.11. Turn `BR2_PACKAGE_GST1_PLUGINS_BAD_PLUGIN_WAYLAND` off.
- 2.52 needs `-DUSE_LIBHYPHEN=OFF` (no libhyphen in buildroot-nc4).
- WebKit 2.50.5 with JIT on fails CMake configure under cmake 4.4: an unquoted empty `${_linked_into}` in `_WEBKIT_TARGET_LINK_FRAMEWORK` gives "Unknown arguments specified" at the LLIntSettingsExtractor target. CLoop builds never hit it. That was patch 0005. It is fixed upstream in 2.52, so 0005 does not exist in the 2.52.6 set.
- HTTPS needs glib-networking and ca-certificates.
- Packaging: `browser/host/bundle.sh` in the container, `browser/host/make_ipk.py`. ipk 63 MB, 133 MB installed, 78 libraries. `browser/host/deploy_host.sh` swaps only the host binary.
- Keep each installed ipk locally (it was kept under `build/ipk-<version>/`, not versioned and since deleted). A same-hour A/B against an older build otherwise needs a rebuild.
- Docker in colima sees `/Users`, not `/private/tmp`. Keep container inputs under the project (`browser/build/`).

### Why 2.52.x and not 2.54

- WebKit removed softfp support in 252034@main (bug 242172, 2022-06). It cannot be cleanly reverted, because the MIPS FP-in-GPR path it relied on is gone.
- 2.50 enables the 32-bit ARM JIT only for `CPU(ARM_THUMB2) && CPU(ARM_HARDFP)` on Linux (`PlatformEnable.h:640`). `-mthumb` does not help. The cause of kimjione's "DFG and FTL JIT require baseline JIT" is softfp. An earlier "ARM mode" explanation was wrong.
- Removing the gate alone is unsafe: JIT calls into C++ operations would pass doubles in the wrong registers and silently corrupt values. Patch 0006 fixes the C++ side.
- 2.54 hard-disables the JIT for every `JSVALUE32_64` target (`#if USE(JSVALUE32_64) #undef ENABLE_JIT`). The ARMv7 JIT sources stay in the tree but are not built or tested. Latest stable was 2.54.2 (2026-10-23).
- So the 32-bit browser stays on 2.52.6, the last branch with the ARMv7 JIT. 2.54 only makes sense on the 64-bit path. WPEPlatform became the default API in 2.54.

### Patches

| Patch | What | Why |
|---|---|---|
| libgcrypt 0001 webos-use-urandom | Gather entropy from `/dev/urandom` | The TV has no `/dev/random`. libgcrypt dies with "no entropy gathering module detected" |
| wpebackend-fdo 0001 webos-memfd-fallback | Provide `memfd_create` via syscall 385 plus `MFD_*`/`F_ADD_SEALS` | The build glibc lacks them |
| 0001 webos-madv-dontdump | Define `MADV_DONTDUMP` 16 and `MADV_DODUMP` 17 | Old glibc headers lack them (bmalloc) |
| 0002 webos-roundeven-fallback | Use the existing fallback for `roundeven` | glibc older than 2.25 lacks it |
| 0003 skia-arm32-softfp-abi | Use the aapcs-vfp stage ABI only with `__ARM_PCS_VFP` | Skia used it whenever NEON was on. Gradients and shadows broke under softfp |
| 0004 webos-exec-path-env | Always read `WEBKIT_EXEC_PATH` | It was read only in DEVELOPER_MODE. The engine lives inside the app dir |
| 0005 | (dropped) cmake 4 quoting in WebKitMacros.cmake | Fixed upstream in 2.52 |
| 0006 softfp-jit-vfp-pcs | Open the ARMv7 JIT gate on softfp. `JIT_OPERATION_ATTRIBUTES` (`WTF/wtf/PlatformCallingConventions.h:82`) = `__attribute__((pcs("aapcs-vfp")))` | JSC assumes the VFP PCS for every JIT/C++ call (FPRInfo d0-d7 args, `setupArguments` in d-registers, result in d0) |
| 0007 webos-pson-env | Env `WEBKIT_DISABLE_PSON` turns off process swap on navigation | WPE hardcodes `setProcessSwapsOnNavigation(true)`. The `psonEnabled` property is GTK3-only and the preference is not in `webkit_settings_get_all_features`. Each cross-site navigation left a 170-250 MB process alive plus a 16 MB prewarmed one |
| 0008 jsc-wasmorigin-needs-webassembly | Guard `WasmOrigin` with `ENABLE(WEBASSEMBLY)` | A JIT-on, WASM-off build does not compile |
| 0009 dfg-fold-math-keep-vfp-pcs | Call DFG constant-fold Math functions through a typed `Arith::UnaryFunction` lambda | GCC drops pcs attributes through a deduced template argument, without a warning. `Math.log(10)` folded to NaN, sin/cos/exp wrong |
| 0010 yarr-jit-armv7-keep-r4 | Save r4 before `generateEnter` writes the new sp into regT0 = r4 | Caller's r4 was clobbered |
| 0011 regexp-compiler-thread-no-relock | No `cellLock` re-entry when the compiler thread falls back to bytecode | `matchInline` re-took the non-recursive lock held by `matchConcurrently` on JITCodeFailure: deadlock at ~0% CPU |
| 0012 yarr-jit-armv7-fifth-arg | Read the 5th argument (`MatchingContextHolder*`) at `[fp + 8]` | It read `[fp + POKE_ARGUMENT_OFFSET(0)]` = the caller's saved r7. Crashes depended on the caller (DFG paths) |
| 0013 system-heap-align-16 | bmalloc SystemHeap returns 16-byte aligned blocks: plain malloc plus 20 B slack, pointer rounded to 16, offset word below it, realloc grows in place | glibc malloc aligns to 8 on arm32. GCC stores alignas(16) members with `:128` NEON stores. SIGBUS in `WebPageProxy::resetState` |
| 0014 sticky-no-relayout-on-scroll | In `LocalFrameView::setBaseLayoutViewportOrigin` mark only fixed renderers needsLayout. Sticky layers get `setNeedsCompositingGeometryUpdate` and a scheduled compositing update | Every scroll relayouted every sticky box. Wikipedia's pinned TOC (sticky + overflow auto) cost 15-47 ms of layout per frame |
| 0015 cssjit-armv7 | CSS selector JIT for ARMv7 Thumb-2 | The selector compiler existed only for x86_64 and ARM64 (`PlatformEnable.h:975`). 33% of the main thread on a Wikipedia load was `SelectorChecker` |

Patch notes:

- 0006 was first kept in `browser/buildroot/patches-jit/` and is now part of the main set.
- 0006: GCC 16 honours `pcs("aapcs-vfp")` under softfp. The attribute is not part of the type. It is dropped when a function pointer goes through a template. Usually that gives `-Wignored-attributes`. Grep the build log. 31 drops, none on a signature with double or float. 0009 is the case where no warning appeared. Verified with `g++ -S`: via template `bx r3` softfp, via typed pointer or lambda `vmov d0`.
- 0006: keep WebAssembly off. IPInt, Air and B3 carry their own VFP assumptions. FTL is off. Runtime switches still work (`JSC_useJIT=0`, `JSC_useDFGJIT=0`). JIT off falls back to the asm LLInt, still faster than CLoop.
- 0009: the only C++ call site of `Arith::UnaryFunction` is the DFG abstract interpreter (`DFGAbstractInterpreterInlines.h`). Other folds call `operationMathPow` and `Math::roundDouble` directly and keep the attribute. mathfold: 36 of 71 wrong before, 0 after. Before the fix Speedometer's Perf-Dashboard hung (toPrecision RangeError).
- 0010-0012: real upstream bugs in the ARMv7 YARR path. They were never exercised because upstream sets `useRegExpJIT = jitEnabledByDefault() && is64Bit()`. The host sets `JSC_useRegExpJIT=true`. Without the patches `--useRegExpJIT=true` passed 18 simple shapes but crashed in regexp-octane.
- 0013 v1 used glibc `aligned_alloc` and copied on every realloc. It cost about 15% (Speedometer 0.62 vs 0.73, wheel-wiki 25 vs 32 fps). v2 is within noise.
- 0013 is needed on cortex-a9 builds too. The a9 lib has 516 `:128/:256` NEON accesses, the a55 lib 711.
- 0014 v1 without the compositing update broke sticky (the TOC scrolled away). Chromium computes sticky offsets without layout.
- 0015: registers r0-r3 caller-saved, r4 r5 r8-r11 callee-saved, r6 = addressTemp, ip = dataTemp, r7 = fp excluded. Pushes r6 and lr/r7, keeps sp 8-aligned at helper calls, uses `sdiv` for `:nth-child` modulo. Enabled only for `CPU(ARM_THUMB2) && HAVE(ARM_IDIV_INSTRUCTIONS)`, true only with `-mcpu=cortex-a55`. `CannotCompile` above 10 registers. Generator: `browser/build/cssjit_armv7.py`. Correctness: `pages/selcheck.html` fingerprint (1204 sheet selectors, 37 synthetic, computed-style hash of 11652 elements) identical with and without the JIT.
- Port to 2.52.6: 0007 was rewritten (configuration is a pointer). 0001-0004 and 0006 were regenerated and apply with `-F0`. 2.50.5 patches are kept in `browser/buildroot/patches-2.50.5`.

### Host runtime settings

- `WEBKIT_DISABLE_PSON` (patch 0007).
- `Malloc=1` (bmalloc falls back to system malloc, see crash A).
- `LD_PRELOAD=<app>/lib/libmimalloc.so.2` (mimalloc v2.1.7, 75 KB, `browser/mimalloc/build_mimalloc.sh`). Launch param `env=LD_PRELOAD=` disables it.
- `JSC_useRegExpJIT=true` unless the environment overrides it.
- `FONTCONFIG_FILE` to the bundled `fonts.conf`.
- The GIO and GST fixes from section 1.
- User agent: desktop Safari. With `Mozilla/5.0 (Web0S; Linux/SmartTV) ... Safari` Google serves its legacy basic-HTML page.
- Launch param `view=1280x720` renders at 720p and stretches in the host. Trade-off: blurrier text, bigger layout.
- Cache (`XDG_CACHE_HOME`) sits in jail `/tmp`, which is RAM and dies on reboot. Free space on `/media/developer` varies: 155 MB before the 2026-11-11 cleanup, 527 MB before cr151 went in, 1.6 GB after the 2026-11-17 cleanup ([ARTIFACTS.md](ARTIFACTS.md)).
- On-screen keyboard: a `WebKitInputMethodContext` subclass whose `focus_in` calls `SDL_StartTextInput`, and `SDL_TEXTINPUT` emits "committed". The 4-byte SDL ABI shift first delivered garbage text.

### Measured effect

| Change | Date | Effect |
|---|---|---|
| Baseline CLoop, -Os, cortex-a9 | 2026-11-10 | micro 1474 ms (int 593, math 459, objects 349, strings 55, DOM 18) |
| CLoop -O2 -mcpu=cortex-a55 | 2026-11-10 | SLOWER: 1648 and 1619 ms. Compiler flags for CLoop dropped |
| Perf baseline CLoop -O2 | 2026-11-10 | micro 1591, google 2829, wikipedia 3110, youtube 7283 ms |
| 0006 softfp JIT + DFG | 2026-11-11 | micro 363 vs 1591 ms, math checksum correct. Cold page loads unchanged (main thread 85-98% on parse/style/layout) |
| 720p render | 2026-11-11 | rAF 8.5 -> 11.4 fps, screen 26 -> 37, wheel 24 -> 34 |
| 0007 PSON off | 2026-11-11 | 1 web process instead of 3, about 190 MB saved. Warm navigation not faster |
| Upgrade 2.50.5 -> 2.52.6 | 2026-11-11 | JS same. Cold google ~4.2 s vs ~3.2 s (worse). rAF wiki screen 37 -> 56 fps, wheel youtube 2.7-3.6 -> 5.1-5.4 fps |
| Malloc=1 | 2026-11-11 | Perf within noise. Speedometer 3.1 completes: 0.713 and 0.687 |
| RegExp JIT (0010-0012) | 2026-11-12 | jsc regexp-octane 4.5 -> 24.1 pts (64-bit 37). Browser Speedometer 0.720 -> 0.740 (p 0.20) |
| cortex-a55 vs a9 (both 0013 v2) | 2026-11-13 | micro 224 vs 279 ms (-20%), Speedometer 0.744 vs 0.726, wiki load +7% (worse) |
| 0014 | 2026-11-16 | rAF wiki 10 -> 29.7 fps, wiki without JS 18 -> 57, `long.html?box=sticky` 40 -> 60.6. Speedometer 0.73 -> 0.759 |
| 0015 | 2026-11-16 | Style bucket 33% -> 24% of wiki load. Speedometer 0.729 -> 0.738. Post-load busy 5.6 -> 5.3 s |
| mimalloc | 2026-11-16 | Speedometer 0.741 -> 0.825 (+11%), wiki load -4..-9%, RSS +5..+12% on pages (-13% on Speedometer). As default: 0.805 |

Integer division: JSC's `HAVE(ARM_IDIV_INSTRUCTIONS)` is compile-time (`__ARM_ARCH_EXT_IDIV__`). With cortex-a9 tuning, `s += i % 7` over 3e7 iterations took 9.1 s vs 0.27 s with `& 7` (0.51 s on 64-bit). This is why the a55 build wins micro.

Skia modes (2026-11-11, rAF fps / screen fps): default CPUAffineRendering hybrid won. `WEBKIT_SKIA_ENABLE_CPU_RENDERING=1` 7.5/25, GPUAffineRendering 6.5/18.5, CPU with 3 threads 0.6/16.5. Host swap takes 3-4 ms, so presentation is not the limit.

Final comparison with the other engines: see the table in section 6.

### Crash history

- Crash A (2026-11-11): SIGSEGV in `JSObject::allocateMoreOutOfLineStorage` from `putDirectInternal`, on Speedometer and rare cold loads. First suspected JIT. Core anatomy: the butterfly at 0xd3800008 straddled the end of a mapped 1 MB region. It still crashed with `JSC_useJIT=0`, `useGenerationalGC=0` and single-marker non-concurrent GC. With `Malloc=1` Speedometer completes. Root cause: bmalloc on this platform (suspects patch 0001 defines or kernel 4.4). Not fixed in bmalloc, avoided with `Malloc=1`.
- 1 crash in 25 cold loads with JIT on both 2.50.5 and 2.52.6. 0 crashes in a separate run of 12 loads with and 12 without JIT. Too rare to attribute. Load times with and without JIT were the same.
- Font crash (2026-11-11): deterministic SIGABRT on Speedometer via `FontCache::lastResortFallbackFont` -> `fontForPlatformData` (FontCacheSkia.cpp). Empty last-resort typeface because "serif" matched nothing. Not JIT. Fixed with the bundled `fonts.conf`. Likely behind some of the rare crashes.
- Crash B: SIGSEGV in `CoordinatedPlatformLayer::setOwner` from `ScrollingTreeCoordinated::applyLayerPositionsInternal`. Symbolized against a relinked lib, so approximate. Not reproduced.
- A55 SIGBUS (2026-11-12): not JIT. See patch 0013. `jsc` with `LD_LIBRARY_PATH` pointing at a new lib smoke-tests it without the browser.

### Profiles

- YouTube desktop cold load: main thread 14.9 s CPU of 15 s (saturated), JITWorker 5.0 s, SkiaGPUWorker 2.1 s. Timeline: JS 13.7 s of 15.7 s self time (87%), mostly the `kevlar_base` bundle. YouTube is JS-bound.
- Wikipedia cold load (perf): style 33%, other 17%, layout 15%, JS 11%, alloc/libc 9%, gpu+kernel 6%, DOM 5%, paint 5%. Style/layout-bound.
- Post-load busy time on Wikipedia: WPE fires load before the first full style and layout. Load 3.2 s, then it settles 5.6-5.7 s later with 5.5 s busy (stock Chrome 87: load 4.7-5.7 s, then 1.2-1.3 s). Without page JS WPE fires load at 0.8 s and settles 4.5-4.9 s later (about 5.7 s from start, stock 5.5 s). `load_ms` alone flatters WPE.
- YouTube wheel scroll at about 5 fps is a start-up artefact: YouTube keeps the main thread about 100% busy with timers and MutationObserver for 20 s after load. After settling: 35-40 frames/s. YouTube wheel scrolling runs on the main thread, not on "Core: Scrolling".
- Wikipedia wheel scroll: 60 fps after the page settles (case `wheel-wiki-settled`), 32 fps 2 s after load.
- Reddit (new UI): web process grows to about 550 MB RSS, main thread about 93% for 20+ s, one load took 42 s. old.reddit.com redirects logged-out users to `/login`.
- JetStream 3 does not finish: web process RSS 205-380 MB for 20 min, then about 1.0 GB RSS / 1.87 GB VmSize at 25 min and memchute kills the app. Culprit subtest not identified.

### Video in WPE

- 2026-11-16: all software (`av:h264:df*`, `vpx_tile_worker`). LG `lxvideodec` cannot be used with a bundled GStreamer.
- h264 1080p30 about 14 fps (197 frames in 14 s), h264 1080p60 48 frames, VP9 1080p60 and 4K and HEVC 4K stall. AV1 not supported. No EME at all. The software path is presentation-bound (`vqueue:src` heavy, decoders about 55% each).
- WebKit 2.50 has hole-punch quirks (`WEBKIT_GST_HOLE_PUNCH_QUIRK=westeros`: element `westerossink`, property `rectangle` "x,y,w,h", `zorder`, sink caps added to the decodebin stop caps). Unused.

### Open issues (frozen)

- No hardware video, no EME.
- bmalloc root cause (crash A) unknown.
- JetStream 3 memory kill.
- On-screen keyboard text input not confirmed on the TV.

## 4. 64-bit path (frozen)

- The aarch64 kernel runs aarch64 binaries that bring their own loader: `$J/lib/ld-linux-aarch64.so.1 --library-path $J/lib $J/jsc bench.js`. One harmless warning about the 32-bit `/lib/libSegFault.so` preload.
- Debian trixie `jsc` 2.54.0 arm64 (22 libs, 81 MB) on micro: 126-142 ms vs 227 ms for the 32-bit JIT in the browser (different versions).
- Same-version A/B on 28 JetStream-lite tests (2026-11-12, `browser/bench/jsall.sh`, each test its own process, `--no-prefetch` because 32-bit jsc has no Wasm): own aarch64 jsc 2.52.6 (DFG+FTL) vs own 32-bit 2.52.6 (DFG, RegExp JIT, Malloc=1): geomean 1.62x (0.88 octane-code-load to 2.99 hash-map). Median peak RSS 90 MB (64) vs 120 MB (32). 64-bit costs no memory here.
- An earlier cross-version run (Debian jsc 2.54.0 64-bit against our 32-bit 2.52.6, before the RegExp JIT fix) gave geomean 1.79x (1.72x with Malloc=1 on both), regexp-octane 7.8x. richards: 90.7 (64) vs 40.4 (32).
- `json-*-inspector` tests fail in the shell in every mode.
- WPE composites with GL (TextureMapper) even with CPU painting. A 64-bit WPE therefore needs GL: the bridge or Mesa llvmpipe.
- The bridge: GPL-3, aarch64 libEGL/libGLESv2/libwayland shims that forward every call over shared memory to a 32-bit `gles_proxy`. It bundles glibc and ld-linux-aarch64 via patchelf. v0.0.1-0.0.8 (2026-06 to 2026-10), aimed at RetroArch and Kodi, tested on webOS 10/11, "roughly" webOS 6+.
- Bridge build recipe (`browser/bridge64`): v0.0.8 plus the 12 patches from issue #1 (`git am`, all apply). `make` with `CC_32`, `SYSROOT_32`, `CC_64`, `SYSROOT_64`, `WAYLAND_PROTOCOLS_64=$SYSROOT_32/usr/share/wayland-webos`, `STRIP_64_CMD`, `PATCHELF`, `PROXY_INSTALL_PATH`, `BRIDGE_CONFIG_PATH`, `LOG_FILENAME`. wayland-scanner needs `LD_LIBRARY_PATH=<w64>/output/host/lib`. The wayland stub links `libwayland-client-real.so.0`. Ship the real aarch64 lib under that name.
- buildroot-nc4 ships only 32-bit target toolchains. aarch64 needs upstream buildroot (`browser/buildroot64`).
- aarch64 WebKit with WPEPlatform and MiniBrowser needs `-DENABLE_WPE_PLATFORM_DRM=OFF` (DRM wants libinput) and `-DUSE_GSTREAMER=OFF` when multimedia is off (ANGLE code includes gst headers).
- Headless engine on the TV (2026-11-12): MiniBrowser `--headless`, WPEPlatform headless, Mesa llvmpipe, Release -O2, FTL on. JIT works in the web process. mathfold 0/71 wrong.
- Results: YouTube cold load 15.5 s vs 10.1 s on 32-bit. Speedometer 0.356 against 0.725 on 32-bit, and 0.632 with CPU rendering against 0.744 on 32-bit.
- Why: SkiaGPUWorker used 19 s CPU in 17 s (Skia GPU raster on llvmpipe). `WEBKIT_SKIA_ENABLE_CPU_RENDERING=1` brings YouTube to 13.3 s. `LP_NUM_THREADS=0` gives 14.1 s. In the Timeline both builds spend about 14 s of main-thread JS. EvaluateScript was 7.2 s on 64-bit vs 6.2 s on 32-bit. The 1.6x shell advantage does not show in the page.
- Blockers: Mali EGL/GLES and StarfishMediaAPIs are 32-bit only. Display needs the bridge or CPU raster plus a 32-bit presenter. Hardware video needs a 32-bit helper over IPC. CSS selector JIT would come for free on ARM64.
- Status: frozen. Headless llvmpipe numbers understate the engine, but no path to a 64-bit display was built.

- Running the 64-bit headless WPE: `buildroot64/bundle64.sh`, then `run64.sh <url>` on the TV. The inspector listens on :9223 (`$DEVTOOLS_ADDR`). Drive it with `bench/probe.py`, `bench/eval.py` and `bench/timeline.py`.

## 5. Chromium 120 from webOS OSE (cr120, frozen fallback)

Source: [webosose/chromium120](https://github.com/webosose/chromium120). Built from a git clone of that repo plus a Debian buster sysroot. Nothing is fetched from third-party ports at build time. Kept as the fallback built from verified sources.

### How OSE builds it

- Full `src` snapshot (2.4 GB packed) with depot_tools and gclient files. README says it builds only inside OE ([meta-webosose](https://github.com/webosose/meta-webosose)).
- OE recipe `meta-webos/recipes-webos/chromium/webruntime*.bb`. Default `webruntime-clang_120.bb`: `is_clang=true`, `target_sysroot` = OE sysroot, `ARM_INSTRUCTION_SET=arm` (tcmalloc breaks with `-mthumb`).
- `arm_float_abi` comes from `TUNE_FEATURES`. softfp unless `callconvention-hard`, so softfp is a supported config.
- Targets: `webos:weboswebruntime` (libcbe.so), `app_shell`, `browser_shell`, `chrome`.
- GN: `is_webos=true`, `use_ozone`, `use_cbe`, `is_app_shell_cbe`, `use_pmlog`, `use_x11=false`, `//neva/gow.gn` (Google ozone wayland) and `//neva/iow.gn` (Intel ozone wayland in `src/ozone`).
- `src/ozone/wayland/shell` has `wl_shell_surface`, `webos_shell_surface`, `xdg_shell_surface` and ivi. The Intel backend matches the C1 compositor. webOS parts are gated by `is_webos` and pkg-config `wayland-webos-client`.

### Build setup (`browser/cr120`)

- Image `cr120`: Ubuntu 24.04 arm64, clang/lld 18, qemu-user-static. Volume `cr120`: `/w/chromium120` via `git clone --depth 1` (15.4 GB, 632k files, third_party complete, no gclient sync). gn built from source at DEPS `gn_version` e4702d74.
- The build host is an aarch64 colima VM on Apple silicon. The repo's x86_64 clang does not run (binfmt has only qemu-i386/x86_64, no rosetta). Apple silicon cannot execute AArch32, so V8 snapshot tools run under `qemu-arm-static`.
- Sysroot: Debian buster armel via `debootstrap --foreign` (glibc 2.28 = TV). `--foreign` leaves `--include` packages in `var/cache/apt/archives`. Unpack them with `dpkg-deb -x`.
- Chromium's `pkg-config.py` searches only `<sysroot>/usr/lib/pkgconfig` and `usr/share/pkgconfig`. Link multiarch `.pc` files there, for the target and the host sysroot "/".
- A `.pc` with bare `-I${includedir}` = `/usr/include` puts the sysroot include dir before libc++ ("<cmath> tried including <math.h> but didn't find libc++'s"). Strip it where `includedir=${prefix}/include`. Not in `nss.pc`, which points at `/usr/include/nss`.
- Host arm64 toolchain: sysroot "/" via symlink `build/linux/debian_bullseye_arm64-sysroot`, glib and nss dev packages in the image. `third_party/node` is x86_64: symlink the system node.
- devtools-frontend esbuild is x86_64: use npm `esbuild-linux-arm64` 0.14.13.
- crashpad wants libcurl: `crashpad_http_transport_impl="socket"`.
- `is_webos=false` with patch 0002. `use_neva_appruntime` must stay true: false does not compile (`display_damage_tracker.cc` defines `OnSurfaceActivatedEx` unguarded). No atk, no pangocairo, no plugins/ppapi, no pipewire. Set `neva_dcheck_always_on=false`.
- OSE drops `content/test/data`. content_shell needs two mojom files from upstream 120.0.6099.269 (`browser/cr120/extra`).
- OSE `content/browser` includes `chrome/browser/web_applications` headers with no gn dep on their mojom/proto targets. Random "mojom.h/pb.h not found". `browser/cr120/genheaders.py` prints the gen headers to build first (repeat until empty).
- Wayland: use Debian buster's wayland-scanner 1.16 (`libwayland-bin_1.16.0-1_arm64.deb`) via env `WAYLAND_SCANNER`. Editing the wrapper regenerates every protocol. Sysroot uses the NDK's wayland client headers and libs, plus `wayland-text-client-protocol.h` and `curses.h` (`webos_text_input` takes `KEY_*` from curses, like OE).
- libwayland-egl: buster has soname `.so.1`, the TV has Mali's `.so.0`. Bundle `lib/libwayland-egl.so.1` as a symlink to `/usr/lib/libwayland-egl.so.0`.
- content_shell is 42k ninja steps. Any compiler or BUILD.gn flag change, or a change to `neva:config` defines, rebuilds everything.
- `build.sh` copies `extra/` with `cp -ru`. With `-n` edits to overlay files never reached the tree.
- media/neva code cannot use `base::ScopedAllowBaseSyncPrimitivesOutsideBlockingScope` (private ctor). Do blocking reads and process reaping on `base::ThreadPool` with `MayBlock`.

### Patches

| Patch | What | Why |
|---|---|---|
| 0001 v8-run-arm32-tools-under-qemu | Run 32-bit ARM host tools (mksnapshot, torque) through `qemu-arm-static` with the target sysroot | An arm64 build host cannot execute AArch32 |
| 0002 ozone-wayland-webos-shell-only | Build webOS shell sources and define `OS_WEBOS` only inside `src/ozone/wayland` | The C1 shows only `wl_webos_shell` surfaces. Global `is_webos` pulls in too much |
| 0003 softfp-target-triple | `--target=arm-linux-gnueabi` when `arm_float_abi != "hard"` | `arm-linux-gnueabihf` picks `ld-linux-armhf.so.3`, absent on the TV |
| 0004 no-atk | `use_atk = false` | No atk in the sysroot |
| 0005 clang18-warnings | `-Wno-c++11-narrowing-const-reference`, `-Wno-error=unknown-warning-option` | Released clang 18 errors in webrtc code that predates it |
| 0006 app-runtime-locales-dep | Add `:repack` dep to `neva/app_runtime:locales_repack` | With `use_cbe=false` gn reports "Input to target not generated by a dependency" |
| 0007 content-shell-test-stubs | Update content/test and web_test stubs (6-arg `DisplayPersistentNotification`, `SetFirstActivateTimeout`) | OSE changed interfaces that its own build never compiles |
| 0008 paint-event-and-wayland-scanner | Guard `kFirstContainerResetPaint`. Honour `WAYLAND_SCANNER` in `wayland_scanner_wrapper.py` | The enum is `OS_WEBOS`-only. The in-tree scanner (1.21+) emits `wl_proxy_marshal_flags`, absent in libwayland 1.11 |
| 0009 pal-pc-factory-signatures | Sync the PC pal factory with `pal_platform_factory.h` | Declarations drifted |
| 0010 gn-run-binary-arm32-under-qemu | qemu prefix in `build/gn_run_binary.py` | `v8_context_snapshot_generator` is a target binary |
| 0011 content-shell-neva-link | Link watchdog switches, CORS/CORB exception list, stubs (`extra/content/shell/neva_c1_stubs.cc`) | content_shell links neva code that only the webOS app shells provide |
| 0012 neva-media-luna-client | Build the webOS UMS player with `WebOSMediaClientLuna` (`extra/media/neva/webos/webos_mediaclient_luna.*`) | No g-media-pipeline on the TV. `UMediaClientImpl`'s base class is in the libstdc++-built `libumedia_api` |
| 0013 neva-media-position-non-webos | Use `GetPosition()` adjusted to `TimeTicks::Now()` | `get_position()` exists only under `OS_WEBOS` |
| 0014 viz-video-hole-for-ndl | Draw `VideoHoleDrawQuad` as a transparent `kSrc` hole, keep an alpha root pass, report the hole rect to ozone. Only when `$CN_MEDIA_SOCK` is set | NDL video plane under the page. From WebOS-Chromium patches 0024 and 0026 (BSD-3), rebased |
| 0015 ndl-hardware-video-wiring | Renderer uses `CnNdlRendererFactory`. ozone starts `cn_video_export`, names the window `$APPID` instead of `com.webos.app.N`, sends no opaque region | LSM would hide the plane. Wiring for the NDL port |

### GPU on Mali

- Intel ozone allows only `egl-gles2`, no ANGLE ("Requested GL implementation (gl=egl-angle...) not found"). Chromium 120 desktop Linux has only the passthrough decoder, which needs ANGLE: FATAL "Passthrough is not supported, GL is egl". Fix: gn arg `enable_validating_command_decoder=true`. The switch `--use-cmd-decoder=validating` alone is ignored.
- Mali then reports `GL_UNKNOWN_CONTEXT_RESET_KHR` 1-4 s after start in every GPU process. After 7 tries "GPU process isn't usable". Fix: `--disable-gl-extensions=GL_EXT_robustness GL_KHR_robustness`.
- GPU raster draws some content images as solid green boxes. Not YUV decode (`--disable-features=DecodeJpeg420ImagesToYUV,DecodeLossyWebPImagesToYUV` does not help), not `texture_rg`. `--disable-gpu-rasterization` fixes it at a small cost. Unsolved in cr120, solved in cr151.
- Foreground policy: `src/ozone` `window.cc` sets the `wl_webos_shell` appId property to `com.webos.app.<n>` (first window = `com.webos.app.1`). With content_shell on screen `getForegroundAppInfo` returns that id, and uMediaServer gives it HW decoders (HEVC 4K on HEVCP1_HEVC at about 0.5% of a core).
- content_shell's window defaults to 800x600 and LSM stretches it. Pass `--content-shell-host-window-size=1920x1080`.

### Results (2026-11-16, GPU raster 3 rounds, SW raster 2 rounds + 2 YouTube runs, `browser/cr120/RESULTS.md`)

| Case | cr120 GPU raster | cr120 SW raster | WPE 2.52.6 | Stock Chrome 87 |
|---|---|---|---|---|
| micro | 270-295 ms | 259-309 ms | 232-264 ms | 334-355 ms |
| load-wiki | 3.6-4.7 s | 3.1-3.3 s | 3.2-3.3 s | 4.8-5.0 s |
| raf-wiki | 59.7-60.3 fps | 61.4 fps | 10 fps (before 0014) | 59-60 fps |
| Speedometer 3.1 | 0.606-0.613 | 0.581-0.596 | 0.744 | does not start |
| YouTube load | 7.24-7.34 s, FCP 1.8 s | 7.6-8.3 s | 10.1 s | not measurable |

The stock browser is `com.webos.app.browser`, an LG Chromium fork (UA Chrome/87.0.3945.79 "Colt/2.0", main code `lib/libcbe.so`). Speedometer 3.1 does not start on it: it loads its modules and goes idle. Missing JS features are likely, not verified.

### Video path history

1. Software (2026-11-16): FFmpeg h264, libvpx, dav1d. h264/AV1 1080p30 real time at about 1.3 cores. 1080p60 h264/VP9 near real time with drops at 3+ cores. VP9 4K about 1/3 speed. HEVC NotSupported. EME ClearKey only.
2. uMediaServer via luna-send (patches 0012, 0013, `use_neva_media=true`): one `luna-send` per call and one `luna-send -i` subscribe stream per pipeline. h264+AAC `<video src>` on G1_H264 at about 10% of one core (vs 1.75 cores software). Video-only clips stall after 0.2-0.5 s. OSE has no platform MSE path (no `media_platform_api`), so YouTube stays software. The OSE gate is `is_webos && use_gst_media` (pkg `gmp-player-client`, absent on the TV, and the NDK `gmp.pc` is GNU MP). TV `libumedia_api.so.1` uses libstdc++ `std::__cxx11::string`, Chromium uses libc++ `std::__Cr`. Rebuilding Chromium on the TV's libstdc++ (gcc 8, no C++20) is out.
3. NDL port from WebOS-Chromium (2026-11-17, patches 0014, 0015): dev app `com.viiees.cr120`, main = `launcher/cr120run` (SAM-launched ELF, their `cnrun.c` pattern). It owns NDL and starts content_shell as a child. The renderer sends demuxed video (Annex B, raw VP9, AV1) and PCM audio over `/tmp/cr120/media.sock`. viz punches the hole. The GPU process exports the video window and places the plane. `--disable-web-media-player-neva` sends `<video src>` the same way. `run_tv.sh` (telnet root) remains for non-video benchmarks.

NDL port changes against their 151 code: no `OpusAudioDecoder` in 120 (FFmpeg does Opus), `DecoderBuffer::data()/data_size()`, two track-change methods. Intel ozone has no `wl_webos_foreign` unless `USE_GAV`, so `cn_video_export` binds it on a private `wl_event_queue`. The launcher queues a stream that opens before the window's video id arrives.

| Clip | Mode | Before (2026-11-16) | NDL (2026-11-17) |
|---|---|---|---|
| h264+AAC 1080p30 | src | uMediaServer, 13.4 s | 14.7 s, 0 dropped, ~56 jiffies |
| h264 1080p30 / 60 | src | stalled | 14.8 s, 0 dropped, ~36-43 |
| VP9 1080p60 | src | stalled | 14.8 s, 0/897, ~44 |
| VP9 2160p30 | src | stalled | 14.9 s, 0/451, ~37 |
| AV1 1080p30 | src | stalled | 14.9 s, 0/451, ~27 |
| h264 1080p30 frag | MSE | software, 21/438 dropped, ~1400 | 15.0 s, 0/453, ~24 |
| VP9 1080p60 | MSE | software, 56/641 dropped, ~3700 | 15.0 s, 0/910, ~28 |
| VP9 2160p30 | MSE | software, 26/190 dropped, ~3700 | 15.0 s, 0/455, ~26 |
| HEVC 2160p30 | src | not supported | not supported (mime check) |

- Picture and AAC sound confirmed on screen 2026-11-17, in sync, through ARC.
- YouTube (2026-11-17): 720p AV1 0 dropped at about 21% of a core. 2160p VP9 about 60 fps, 0/2160 dropped, about 1.6 cores, all of it download, MSE append and JS. The first 4K switch once ended in "Something went wrong" (stream flushed, no new open). Not reproduced. YouTube's cookie banner pauses the player until "Reject all".

### Security fixes (2026-11-17)

A review of the code borrowed from WebOS-Chromium (`launcher/cr120run.c`, `cn_ndl_renderer.cc`, `cn_video_export.cc`, patches 0014, 0015) found no malware signs: no network access, no exec except content_shell, writes only logs under `/tmp/cr120`. Three findings in this project's launcher `cr120run.c`, all fixed without a Chromium rebuild and checked on the TV:

1. DevTools was always on (`--remote-debugging-address=$TV_HOST:9224`, no auth). Anyone on the LAN had full control (cookies, JS on any origin, `file://`). Now off unless the launch params contain `"devtools":true`.
2. Argument injection: the `target` launch parameter went into argv unchecked. `--renderer-cmd-prefix=...` would run a command as the app uid. Now only http, https and `about:` URLs pass, anything else becomes `about:blank`, and `--` goes before the URL.
3. Possible SIGBUS: `struct cn_open` (uint64 fields) was dereferenced at an unaligned offset in the socket buffer after odd-sized frames. Now it is `memcpy`'d into a local.

Structural risk remains: `--no-sandbox` with a 2023 engine. A renderer exploit runs as the app uid on a rooted TV.

## 6. WebOS-Chromium 151 (cr151, active direction)

Release under test: `org.nativechromium.browser_0.0.66_arm.ipk` from [sarahahzub/WebOS-Chromium](https://github.com/sarahahzub/WebOS-Chromium), 108 491 662 bytes, sha256 `9ffad27d…b34514` (matches GitHub and the release notes). Chromium 151.0.7922.108, V8 15.1. Installed as a plain dev app (188 MB). Source pin for an own build: `browser/cr151/upstream/COMMIT` = 1499d397a2c7e31121b4202ca734f4d73518517e.

### Trust checks

Done (2026-11-17):

| Check | Result |
|---|---|
| IPK contents | Only `usr/palm/applications/<id>` and `usr/palm/packages/<id>/packageinfo.json`. No postinst or prerm |
| `bin/run.sh` | Byte-identical to `source/package/run.sh` at tag 0.0.66 |
| `ext/tvtools` | Identical to the repo except one comment line in `bg.js` |
| `bin/run` launcher (53 KB) | Imports socket/bind/listen/accept4 only (AF_UNIX media socket). No connect, no getaddrinfo. Matches `cnrun.c` |
| `browser/chrome` (154 MB) | strings show only stock Chromium hosts. No project host, no update URL |
| Auto-update | None. Updates come from Homebrew Channel or manual install |
| Ports | No new LAN listener after first launch. 9222-9226 refused |
| Launch parameters | `run.sh` takes `target` only with http:// or https://. No argv injection |

Not done:

- Proof that `chrome` was built from the published source. The source is complete (pinned chromium151 commit, 44 patches, build scripts), so a rebuild can verify it.
- Memory use (BusyBox ps has no rss).

Structural risks: `--no-sandbox`. TV Tools runs a MAIN-world content script on every page. It sets a webOS TV user agent and filters HLS/DASH manifests by a quality limit.

### Results (2026-11-17, same TV, same harness, stock browser interleaved as control)

| Case | cr151 0.0.66 | cr120 SW raster | WPE 2.52.6 | Stock Chrome 87 |
|---|---|---|---|---|
| micro | 340-345 ms | 259-309 ms | ~230 ms | 335-372 ms |
| load-wiki | 3.5-3.7 s (cold profile 6.4 s) | 3.1-3.3 s | 2.9-3.0 s | 4.9-5.1 s |
| raf-wiki | 62.1-63.4 fps | 61.4 fps | 26-28 fps | 57.4-59.2 fps |
| raf-wiki-nojs | 62.3-64.4 fps | 62.8-63.1 fps | — | 63.6-64.4 fps |
| Speedometer 3.1 | 0.732-0.757 | 0.58-0.60 | 0.80-0.83 | does not start |
| YouTube home load | 5.3-6.1 s warm, FCP 1.2-2.2 s (first two runs 10.1-10.5 s) | 7.6-8.3 s | ~9.9 s | not measurable |

- WPE numbers here include 0014, 0015 and mimalloc. Earlier WPE numbers in section 5 predate them.
- cr151 renders in its own UI at device scale 1.5 (1280x720 DIP minus the toolbar). content_shell renders 1920x1080 at scale 1. Load and rAF compare different viewports.
- Overriding `--js-flags` without `--optimize-for-size` gave micro 332-357 ms. That flag is not the cause of the slower micro. The size build (`optimize_for_size`, LTO without optimisation, no PGO) is the remaining suspect, untested.
- Video: same NDL path as cr120. 0 dropped up to VP9 4K in src and MSE, but about 50-100 jiffies per 8 s against cr120's 24-56 on the same clips. HEVC NotSupported. VP9 profile 2 (YouTube HDR) and E-AC3 unsupported, as in cr120. EME ClearKey only. LG threads `lxvideodec0:src` and `video-src:src` run in the launcher.

### GPU

- On. The launcher log `/tmp/org.nativechromium.browser/media.log` says `gpu: on (EGL 1.4 driver, GPU probe passed)`.
- Their patch 0033 uses `eglGetDisplay(wl_display)` because Mali lacks `eglGetPlatformDisplay`.
- Flags: `--enable-gpu-rasterization --in-process-gpu --use-cmd-decoder=validating`. Images on Wikipedia draw correctly.
- The probe result is cached per boot in `/tmp`. After a GPU crash the launcher turns GPU off (`gpu.state`).

### What it has that cr120 lacks

- Full Chrome UI (tabs, omnibox, bookmarks, settings, extensions).
- LG remote and on-screen keyboard (their patches 0015-0017, 0043), Magic Remote pointer (0045), spatial navigation.
- TV Tools: per-site video quality limit, TV/desktop UA switch, lite mode.
- Profile and cache on flash, a fresh start without restored tabs, memory caps (one renderer, 192 MB JS heap, MSE buffer limits), renice of non-media threads.
- Screensaver guard driven by media session state (their patch 0049).
- One build for webOS 4.4 and newer. Releases every 1-2 days.

It lacks DRM, HEVC and a sandbox. DevTools needs a flag file and a relay.

### Decision

- Use the 0.0.66 build as the Chromium browser instead of cr120. It wins Speedometer (+25%) and YouTube load (-25 to -35%), has working GPU raster on Mali, a real UI and remote support. Video code is the same.
- It loses micro (+11-33%) and wiki load (+6-19%).
- WPE still leads JS but has no usable video and 26-28 fps rAF.
- An own build is worth it for two reasons only: to verify the binary against the source, and to try a speed build for the micro gap. GPU compositing, the screensaver guard and the launcher fixes from cr120 already exist upstream.

### Own speed build plan

- `browser/cr151/Dockerfile`: Ubuntu 22.04 (the upstream sysroot scripts download jammy packages), clang/lld 23 from apt.llvm.org, Rust `nightly-2026-06-17` (the week of Chromium's pinned rustc), Node v24.12.0, ninja 1.12.1, qemu-user-static. Chromium 151 ships clang (llvmorg-23-init) and Rust only for Linux x64 hosts, so arm64 ones are linked into `third_party/llvm-build/Release+Asserts` and `third_party/rust-toolchain`.
- Same `.pc` stripping as cr120 for the host sysroot.
- `browser/cr151/args.delta.gn` is appended to their `source/args.gn` (GN takes the last assignment):
  - `optimize_for_size = false`
  - `thin_lto_enable_optimizations = true`
  - `chrome_pgo_phase = 0` (an arm32 profile is a separate experiment)
  - `arm_version = 8`, `arm_arch = "armv8.2-a"` (ARMv8.2-A has SDIV/UDIV in ARM and Thumb. Plain armv7-a makes every division a libgcc call)
- Patch 0101: `-mtune=cortex-a55` and `-mfpu=neon-fp-armv8` for `arm_version` 8 (`arm_tune` and `arm_fpu` are not GN args in M151), and the armv7 Rust triple for `arm_version` 8 (otherwise rust.gni picks `arm-unknown-linux-gnueabi`, ARMv6).
- Their patch 0012 adds `-mfpu=$arm_fpu`, but `compiler_arm_fpu` appends `-mfpu=neon` after it. Their release runs with plain NEON (2026-11-17, from the ninja command lines). Patch 0101 sets the FPU inside `compiler_arm_fpu`.
- Patch 0100 `webos-no-caption-buttons` (exists): under `OS_WEBOS`, `OpaqueBrowserFrameViewLayout` keeps both button lists empty and ignores `SetButtonOrdering`. The window is always fullscreen, and a minimised window has no taskbar to return from.
- Dead end behind 0100: "Use system title bar and borders" (`browser.custom_chrome_frame=false`) does NOT remove the minimise, maximise and close buttons on webOS, live or after a restart.
- Their build runs on a 64-CPU, 288 GB Modal machine. Ours ran natively in the colima aarch64 VM (12 cores, 24 GB).

### Own speed build: result (2026-11-17)

Dev app `com.viiees.cr151`, details and raw files in `browser/cr151/RESULTS.md`. Against their 0.0.66, interleaved on the same day:

| Case | Own build | Their 0.0.66 | cr120 |
|---|---|---|---|
| micro | 306-370 ms | 346-434 ms | 259-309 ms |
| load-wiki | 2.72-3.14 s | 3.29-4.38 s | 3.1-3.3 s |
| Speedometer 3.1 | 0.825-0.852 | 0.721-0.744 | 0.58-0.60 |
| YouTube warm | 5.4-6.3 s | 5.3-6.1 s | 7.6-8.3 s |

- The size flags were the cause of the load and Speedometer gap, not of the micro gap: micro stays within noise of theirs and behind cr120.
- rAF, YouTube and NDL video do not change. Window caption buttons are gone (patch 0100).
- Cost: chrome 204 MB stripped against 154 MB, 233 MB installed.
- Trust check (`browser/cr151/compare.sh`): NEEDED, exported symbols, URL hosts and version strings match their binary. Not a byte-level proof.

Build traps on an arm64 host (each one cost a rebuild):

- The CIPD gperf in the tree is x86-64. Without binfmt it fails silently and leaves header-only `.cc` outputs, so the link fails much later with undefined `blink::FindProperty` and friends. Use the system gperf and delete the empty outputs (`browser/cr151/clean_gperf.sh`).
- arm32 V8 host tools (mksnapshot, torque) run under `qemu-arm-static`. The sysroot's stub libgcc_s needs GLIBC_2.34 at run time, so qemu needs the real armel runtime: `-L /usr/arm-linux-gnueabi` (patch 0102).
- devtools-frontend ships an x86 esbuild and needs a rollup native addon for arm64 (`prep.sh` replaces both).
- A custom Rust toolchain still needs `third_party/rust-toolchain` linked: some std rules name `rust-toolchain/bin/rustc` directly.

### Operating notes

- Extra Chrome flags: write `/tmp/org.nativechromium.browser/browser.flags` (one per line) AFTER the first launch. The app user must own that dir. `run.sh` chmods it 700.
- Prefs without a remote: CDP on a `chrome://settings` page, `chrome.settingsPrivate.setPref(key, v, "", cb)`. Profile: `/media/developer/apps/usr/palm/applications/org.nativechromium.browser/data/profile/Default`.
- The profile on flash keeps cookies of every site visited during tests.
- The screensaver came on during CDP YouTube runs. Close `com.webos.app.screensaver` before each run.

### UI latency (2026-11-17)

Details: `browser/cr151/UI_LATENCY.md`. Own build against 0.0.66, means over 3 interleaved rounds:

| Chromium metric | Own build | 0.0.66 |
|---|---|---|
| Omnibox.CharTypedToRepaintLatency | 158 ms (ToPaint 72, PaintToPresent 62) | 190 ms (87, 74) |
| Browser.Tabs.TotalSwitchDuration3 | 113 ms | 131 ms |
| EventLatency.KeyPressed.TotalLatency, Down in a page | 162 ms | 215 ms |
| EventLatency.KeyPressed.TotalLatency, Tab in a page (median) | 52-61 ms | 61-170 ms |

- The flags help by 14-25 %, but do not fix the UI.
- Stage split (traces): a Down press in a page spends 130 of 170 ms in the renderer main thread. The cause is
  `--enable-spatial-navigation` in their run.sh: each arrow walks all candidates, about 3750 forced
  `Document::UpdateStyleAndLayout` calls per key on a Wikipedia page. `--blink-settings=spatialNavigationEnabled=false`
  in browser.flags turns it off (it survives `ApplyWebPreferences`): Down 162 → 36 ms, Tab 192 → 91 ms (mean). Arrows then
  only scroll.
- `--disable-gpu` makes everything slower (omnibox PaintToPresent 58 → 150 ms). The omnibox cost is browser main-thread
  work (Views layout, paint, autocomplete updates). Spatial navigation and GPU do not change it.
- A second `--disable-features` in browser.flags would replace run.sh's whole list, because the last switch wins.
- Key injection: writing `struct input_event` into `/dev/input/event10` ("LGE Network Input") gives real keys
  through the compositor (`bench/evkeys.c`). `event1` ("LGE RCU") is not read by the compositor, so keys written
  there are lost without an error. Ctrl combos work. F6 focuses the omnibox, Ctrl+L right after launch went to the page.
- `Browser.getHistograms` returns browser-process histograms only. Renderer ones (`EventLatency.*`) appear after
  the browser fetches them from children, which `chrome://histograms` in a background tab triggers.
- `Event.Latency.OS2.KEY_PRESSED` is always 0 on webOS, so the time from the remote to Chromium is not visible.
- zig cc for small TV tools needs `-fPIE -pie`. Without it the binary segfaults before main.

## 7. Tooling gotchas

### Moving files

- `tvput.py` over telnet moved about 3 MB/min and stalled at 30 MB (the TV rebooted).
- `browser/host/tvstream.py` streams one telnet session into a single `base64 -d` with `stty -echo`: about 5 MB/s, md5 checked. Use it.
- `browser/host/tvfetch.py` pulls files back the same way (about 5.8 MB/s).
- The TV's curl to an http.server on the build Mac got "Connection reset by peer" (Mac sandbox or firewall). `nc -l` on the Mac was denied. The TV's nc cannot listen.
- A script uploaded with `tvstream.py` is not executable. `chmod +x` it or call it via `sh`.
- `deploy_host.sh` once piped `tvstream` into `tail`, so `set -e` missed an md5 mismatch and an empty file replaced the binary. It now stops on mismatch.
- Install an ipk: copy it to `/media/developer/temp/`, then `luna-send -w 180000 -i luna://com.webos.appInstallService/dev/install '{"id":"com.ares.defaultName","ipkUrl":"<path>","subscribe":true}'`.

### Telnet sessions

- A single telnet session that launches the browser, sleeps and then prints a report sometimes never delivers its END marker. The client returns at its 180 s deadline with a cut transcript. Launch, sleep (on the Mac) and report in separate sessions. The same report alone returns in about 1.4 s.
- BusyBox `ps` and `pkill` in one telnet session do NOT see processes started from an earlier session. They looked dead and 10 instances piled up. Find and kill via `/proc/[0-9]*/comm` and `xargs kill -9`.
- `grep -l pattern /proc/*/cmdline` matches the grep itself. Use patterns like `'nosave[r]'`.
- Abort a benchmark when the TV's `btime` changes (it rebooted).

### Screenshots

- `luna://com.webos.service.capture/executeOneShot` with `"method":"DISPLAY"` (PNG or JPEG), fetched with `tvfetch.py`. Graphics plane only. The video plane needs a human.

### DevTools and inspector binding rule

- Bind DevTools or the Web Inspector to the TV's LAN IP only (`$TV_HOST`), never to `0.0.0.0`. Close it after use. A remote debugging port gives anyone on the LAN full control of the browser: cookies, JS on any origin, `file://`.
- Never leave it on by default in a shipped launcher. cr120 turns it on only with `"devtools":true`.
- WPE: `ENABLE_REMOTE_INSPECTOR=ON`. Launch env `WEBKIT_INSPECTOR_HTTP_SERVER=$TV_HOST:9222` and `WEBKIT_INSPECTOR_RESOURCES_PATH=/media/developer/temp/inspector` (copy `inspector.gresource` there, or WebKit `g_error()`s on the hardcoded `/usr/share/wpe-webkit-2.0`).
- WPE protocol (`browser/bench/timeline.py`): `Target.sendMessageToTarget`. `Page.enable` is REQUIRED, otherwise every timestamp is 0. There is no `Page.navigate`: use `Runtime.evaluate location.href`. Follow `Target.targetCreated` on cross-site navigation and reconnect. One client at a time.
- content_shell 120 honours `--remote-debugging-address=$TV_HOST`.
- Chromium 151 binds DevTools to 127.0.0.1 only and ignores `--remote-debugging-address`. Use a temporary TCP relay (`browser/cr151/build/tcprelay.c`, built with clang-18 and the cr120 sysroot) and remove it after the run.
- The inspector skews timelines. With the Web Inspector attached, Timeline showed per-frame Layout and Paint of sticky boxes during wheel scroll. Without the inspector the same page did 0 layouts, and Wikipedia wheel scroll ran at 60 fps once settled (2026-11-16 correction). The "wheel ceiling" was start-up JS contention, not the scroll path. A planned patch for async sticky inside `contain: paint` was dropped (`enclosingOverflowClipLayer` already ignores `contain: paint`). Confirm per-frame costs without the inspector, for example with perf or env-gated prints.

### Benchmark pitfalls

- Two engines or sessions sharing one TV collide. A launch of one browser closes the other mid-run, which looks like someone using the remote. Records carry timestamps and lib/host md5, so exclude overlap windows and rerun.
- Before any run check that no other browser runs (`/proc/*/comm`) and that the bench server log is quiet.
- Close the stock browser, YouTube and the screensaver before measuring. The screensaver pipeline also takes decoders.
- A run under the screensaver is void (one YouTube run took 16.0 s under it).
- A launch right after the previous case sometimes does not start (0 web processes, no LOAD). Rerun.
- `load` time alone flatters WPE, which fires load before its first full style and layout. Measure time to settle as well.
- YouTube logged-out home has an empty feed. Different user agents get different payloads (desktop Safari for WPE, Chrome 120 for cr120, a webOS TV UA via TV Tools for cr151).
- YouTube wheel scroll measured during the first 20 s after load measures YouTube's start-up JS.
- Headless 64-bit numbers on llvmpipe understate the engine. Skia GPU raster and llvmpipe threads compete with the main thread.
- Test clips without audio stall in uMediaServer and NDL. Use a clip with an AAC track (`h264aac-1080p30.mp4`, testsrc2 plus 440 Hz).
- `probe.py` once timed out at 600 s although the result was there. Read it with `eval.py`.
- Clips under `/tmp` vanish on reboot. A test then fails at once and the window only flashes.
- Harnesses: `browser/bench/bench.py` (`run --label L`, `compare A B` prints medians, delta and a permutation p), `harness_run.py -b <engine>`, `video_run.py <engine>`, `cdpnav.py`/`navtime.py` for YouTube Navigation Timing, `threadprof.py` for per-thread jiffies, `layers.py` for composited layers, `selcheck.html` for selector correctness, `mathfold.html`/`mathdiag.html` for DFG math folding, `regexjit.js` for RegExp JIT shapes.
- Standard suites: Speedometer 3.1 (`startAutomatically`, `iterationCount`, score in `#result-number`), JetStream 3.0 (`?startAutomatically&tag=js` without Wasm, `#result-summary .score`), MotionMark 1.3.2 (no auto-start, click `#start-button`, `#results .score`). Serve them locally from lighttpd.

### Build host

- Docker on colima (aarch64). After a host reboot the colima VM and its volumes may be gone. Keep build scripts reproducible from scratch.
- `docker pause` frees CPU but not RAM. `colima stop` frees RAM and kills the build, which resumes with `build.sh all`.

- The WPE host logs one `START pid=<pid> params=<json>` line per launch (`host/main.c`). `bench.py` turns a second START into `killed=N`. That is how to tell a memchute autoReload from a manual relaunch.
- State of the TV after 2026-11-17: WPE runs the final library (`a55cssjit` = a55 + 0013 v2 + 0014 v2 + 0015) with mimalloc preloaded by default. cr120, cr151 0.0.66, the own cr151 build (`com.viiees.cr151`) and the benchmark set stay installed. The leftovers of earlier experiments were removed, see [ARTIFACTS.md](ARTIFACTS.md).

## 8. Upstream candidates

None of these has been submitted.

| Patch | Target project | Note | Status |
|---|---|---|---|
| WPE 0008 jsc-wasmorigin-needs-webassembly | [WebKit](https://bugs.webkit.org) | Build fix for JIT on, WASM off | not submitted |
| WPE 0009 dfg-fold-math-keep-vfp-pcs | [WebKit](https://bugs.webkit.org) | GCC silently drops the pcs attribute through templates | not submitted |
| WPE 0010 yarr-jit-armv7-keep-r4 | [WebKit](https://bugs.webkit.org) | Real ARMv7 bug. 2.54 no longer builds the 32-bit JIT | not submitted |
| WPE 0011 regexp-compiler-thread-no-relock | [WebKit](https://bugs.webkit.org) | Deadlock in the concurrent RegExp fallback | not submitted |
| WPE 0012 yarr-jit-armv7-fifth-arg | [WebKit](https://bugs.webkit.org) | Real ARMv7 bug, same caveat as 0010 | not submitted |
| WPE 0013 system-heap-align-16 | [WebKit](https://bugs.webkit.org) | SystemHeap alignment on 32-bit ARM | not submitted |
| WPE 0014 sticky-no-relayout-on-scroll | [WebKit](https://bugs.webkit.org) | Platform-independent scroll performance fix | not submitted |
| WPE 0015 cssjit-armv7 | [WebKit](https://bugs.webkit.org) | New ARMv7 backend for the selector compiler | not submitted |
| cr120 0003 softfp-target-triple | [webosose/chromium120](https://github.com/webosose/chromium120) | softfp outside the OE toolchain | not submitted |
| cr120 0005 clang18-warnings | [webosose/chromium120](https://github.com/webosose/chromium120) | Build with released clang 18 | not submitted |
| cr120 0006 app-runtime-locales-dep | [webosose/chromium120](https://github.com/webosose/chromium120) | Missing gn dep with `use_cbe=false` | not submitted |
| cr120 0007 content-shell-test-stubs | [webosose/chromium120](https://github.com/webosose/chromium120) | Stubs lag OSE interfaces | not submitted |
| cr120 0008 paint-event (first half) | [webosose/chromium120](https://github.com/webosose/chromium120) | Wrong guard on `kFirstContainerResetPaint`. The scanner half is local | not submitted |
| cr120 0009 pal-pc-factory-signatures | [webosose/chromium120](https://github.com/webosose/chromium120) | PC pal factory drift | not submitted |
| cr120 0013 neva-media-position-non-webos | [webosose/chromium120](https://github.com/webosose/chromium120) | Non-webOS build of media/neva | not submitted |
| cr151 0100 webos-no-caption-buttons | [sarahahzub/WebOS-Chromium](https://github.com/sarahahzub/WebOS-Chromium) | Removes minimise/maximise/close on webOS | not submitted |
| cr151 0101 arm-cortex-a55-tune-and-fpu | [sarahahzub/WebOS-Chromium](https://github.com/sarahahzub/WebOS-Chromium) | Fixes the overridden `-mfpu` of their 0012; measured with the speed build | not submitted |
| Platform notes: quoted screensaver timestamp, NDL main-ELF requirement, Mali EGL display | [webosbrew](https://github.com/webosbrew) (documentation) | Knowledge for homebrew authors, not a code patch | not submitted |

