# webOS browser lab

This project looks for the fastest modern web browser on an LG OLED C1 TV running webOS 6.
The TV is rooted. It has 4x Cortex-A55, a Mali-G51 GPU, 32-bit armv7 softfp userspace and an aarch64 kernel 4.4.

Three engines were built, patched and measured against the stock browser (Chromium 87) with the same harness:
- WPE WebKit;
- Chromium 120 from webOS OSE;
- WebOS-Chromium 151.

The goal of this repository is that the next person does not start from scratch. It holds:
- every build recipe and patch;
- the benchmark harness and its method;
- raw results;
- the dead ends, with their reasons.

## Result

| | WebOS-Chromium 151 | Chromium 120 OSE | WPE WebKit 2.52.6 | Stock (Chromium 87) |
|---|---|---|---|---|
| Speedometer 3.1 | 0.73-0.76 | 0.58-0.60 | **0.80-0.83** | does not start |
| micro JS (ms) | 340-345 | 259-309 | **~230** | 334-372 |
| Local Wikipedia load | 3.5-3.7 s | 3.1-3.3 s | **2.9-3.0 s** | 4.8-5.1 s |
| rAF scroll | **62-63 fps** | 61 fps | 26-28 fps | 57-59 fps |
| YouTube load (warm) | **5.3-6.1 s** | 7.6-8.3 s | ~9.9 s | — |
| Video | **hardware, up to VP9 4K, 0 dropped** | hardware (same code) | software, ~14 fps at 1080p | — |
| Browser UI | **Chrome UI, remote, on-screen keyboard** | none (content_shell) | minimal host | LG's |

Method, caveats and every number: [docs/BENCHMARKS.md](docs/BENCHMARKS.md).
Everything learned along the way: [docs/FINDINGS.md](docs/FINDINGS.md).

**Direction: [WebOS-Chromium](https://github.com/sarahahzub/WebOS-Chromium) 151.**
- It wins on scrolling, YouTube and video, has a real browser UI, and the GPU works on the C1.
- The open work is our own build of it, for two reasons:
  - **Speed.** Their release is built with `optimize_for_size` and without PGO. This is the suspected cause of the micro and load gap, not proven yet.
  - **Trust.** Nobody has yet shown that their binaries match their published source.

  The plan and the first patch are in [cr151/](cr151).
- The other engines are frozen. Their code stays here, so any of them can be picked up again.

## Layout and status

| Path | What | Status |
|---|---|---|
| [`cr151/`](cr151) | WebOS-Chromium 151: evaluation of release 0.0.66, own speed build (args delta, patch 0100 removes the window caption buttons) | **active** |
| [`cr120/`](cr120) | Chromium 120 from [webosose/chromium120](https://github.com/webosose/chromium120): content_shell build, patches 0001-0015, NDL hardware video ported from WebOS-Chromium, SAM launcher `cr120run` | frozen: fallback built from LG's published source |
| [`buildroot/`](buildroot), [`host/`](host), [`mimalloc/`](mimalloc) | WPE WebKit 2.52.6 on [openlgtv/buildroot-nc4](https://github.com/openlgtv/buildroot-nc4): patches 0001-0015 (softfp JIT, ARMv7 RegExp JIT fixes, A55 alignment, sticky scroll, ARMv7 CSS JIT), SDL/Wayland host app, mimalloc preload | frozen: fastest JS, but no hardware video and slow scrolling |
| [`buildroot64/`](buildroot64), [`bridge64/`](bridge64) | 64-bit path: aarch64 WebKit over [webosbrew/webos-bridge-64to32](https://github.com/webosbrew/webos-bridge-64to32) | frozen: about 1.6x JS, but EGL and media are 32-bit only on the TV |
| [`bench/`](bench) | Harness, test pages, A/B tool, video test, DevTools clients, raw results | tooling |
| [`perf/`](perf) | Static `perf` for the 4.4 kernel, symbolizer | tooling |
| `build/` | Text evidence of A/B runs, timelines, jsc runs. Binaries are not versioned. | evidence |

Each frozen directory has a `STATUS.md`: what works, what was measured, and where to resume.

## Upstream projects

| Upstream | Used for |
|---|---|
| [WPE WebKit](https://wpewebkit.org) 2.52.6 | WPE engine. Patches in `buildroot/patches/wpewebkit` |
| [openlgtv/buildroot-nc4](https://github.com/openlgtv/buildroot-nc4) @ `322ff04e` | Toolchain and WPE build for webOS (`buildroot/build.sh`) |
| [webosose/chromium120](https://github.com/webosose/chromium120) | cr120 source tree (`git clone --depth 1`) |
| [sarahahzub/WebOS-Chromium](https://github.com/sarahahzub/WebOS-Chromium) (BSD-3) | cr151, and the NDL video path ported into cr120 (`cr120/extra`, patches 0014-0015) |
| [webosbrew/webos-bridge-64to32](https://github.com/webosbrew/webos-bridge-64to32) v0.0.8 (GPL-3) | 64-bit EGL bridge. A fork's patch series is in `bridge64/patches-zip` |
| [microsoft/mimalloc](https://github.com/microsoft/mimalloc) v2.1.7 | Allocator preloaded into WPE (`mimalloc/build_mimalloc.sh`) |
| Linux 4.4.302 `tools/perf` | `perf/build_perf.sh` |
| [webosbrew/SDL-webOS](https://github.com/webosbrew/SDL-webOS) 2.30.12 | Window and input for the WPE host. buildroot's SDL2 has no Wayland driver. Set `SDL_PKG` to a build (lib/ + include/). [mytvlauncher](https://github.com/ViieeS/mytvlauncher)'s `tools/fetch_deps.sh` fetches one |
| [ViieeS/mytvlauncher](https://github.com/ViieeS/mytvlauncher) | Origin of `bench/tvtelnet.py`. `host/make_ipk.py` uses its packaging helpers (`$MYTVLAUNCHER`) |
| Speedometer 3.1, JetStream 3.0, MotionMark 1.3.2 | Benchmark suites, not vendored |

None of the patches have been sent upstream yet. The candidates are listed in [docs/FINDINGS.md](docs/FINDINGS.md#8-upstream-candidates).

## Requirements

- **A rooted webOS TV** with telnet root access, set as `TV_HOST`, and developer mode for installing IPKs.
- **Docker on an arm64 or x86-64 host.** Each engine builds in a named volume:
  - `wpe-br` for WPE;
  - `wpe-br64` for the 64-bit path;
  - `cr120` for Chromium 120;
  - `cr151work` for Chromium 151.

  Volume sizes are 19-23 GB each.
- **Python 3 and ffmpeg** for the tools.

## Security notes

- Chromium 120 and 151 both run with `--no-sandbox` on a rooted TV. A renderer exploit runs code as the app's user.
- The launchers allow only `http`, `https` and `about:` targets. DevTools is off unless explicitly enabled.
- Do not sign in to important accounts until a build is verified.
- Details: [docs/FINDINGS.md](docs/FINDINGS.md).
