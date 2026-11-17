# Chromium 120 (webOS OSE) content_shell: frozen as the fallback

**What it is.**
- Chromium 120 from [webosose/chromium120](https://github.com/webosose/chromium120), built from source on an arm64 host with clang 18.
- It runs as content_shell on the C1.
- Hardware video goes through LG's NDL DirectMedia. That code is ported from [WebOS-Chromium](https://github.com/sarahahzub/WebOS-Chromium):
  - patches 0014-0015;
  - `extra/content/renderer/media/cn_ndl_renderer.cc`;
  - `extra/ozone/wayland/foreign_window/cn_video_export.cc`.
- Video is driven by the SAM launcher `launcher/cr120run.c`, installed as the dev app `com.viiees.cr120`.

**Why it is frozen.**
- WebOS-Chromium 151 is faster on Speedometer, YouTube and scrolling. It has the same NDL video, a real browser UI and working GPU raster. See [docs/BENCHMARKS.md](../docs/BENCHMARKS.md).
- cr120 stays because it is built entirely from LG's and Google's published source. It is the fallback if 151 cannot be trusted or stops being maintained.

## Build and run

- `sysroot.sh`, `build.sh` and `bundle.sh` run in the docker volume `cr120`. The tree is a `git clone --depth 1`.
- Patches 0001-0015 apply on top. The arm32 V8 and GN tools run under qemu on the arm64 host.
- `run_tv.sh` starts content_shell from a telnet root shell. Use it for non-video benchmarks.
  - DevTools binds to `$DEVTOOLS_ADDR`, 127.0.0.1 by default.
  - Set it to the TV's LAN IP to reach DevTools from another machine.
- Hardware video works only inside the SAM app, from `launcher/cr120run.c`.
  - NDL serves only the process that SAM started from appinfo `main`.
  - DevTools is enabled only by `"devtools":true` in the launch parameters.
  - It binds `DEVTOOLS_ADDR`, 127.0.0.1 unless the launcher is built with `-DDEVTOOLS_ADDR='"<TV LAN IP>"'`.
  - `target` accepts only http, https and about: URLs.

Results and history: [RESULTS.md](RESULTS.md).

## Known issues

- **GPU raster** draws content images as solid green boxes on Mali. The workaround is `--disable-gpu-rasterization`. WebOS-Chromium 151 solved this, see its patch 0033 (eglGetDisplay instead of eglGetPlatformDisplay).
- **HEVC** is rejected by Chromium's mime check, although the TV decodes it.
- **EME** offers ClearKey only.
- **`--no-sandbox`.**

## Where to resume

1. Port WebOS-Chromium's GPU fix to bring GPU raster back.
2. Lift the HEVC mime gate.
3. Package a browser UI. content_shell has none.
