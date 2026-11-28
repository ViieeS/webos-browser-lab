# Sources, pinned versions and prior art

This page lists every project this work builds on, the exact version used and what was taken from it.
To reproduce a result, use these versions.

## Test device

| Item | Value |
|---|---|
| TV | LG OLED C1, model OLED55C1RLA, board HE_DTV_W21O_AFABATAA |
| Firmware | webOS TV 6.5.3 (build 6.5.3-47) |
| SoC | 4x Cortex-A55, `perf` cycles counter at 1.686 GHz, no cpufreq in sysfs |
| GPU | Mali-G51, kernel driver mali_kbase r9p0-01rel0. LG ships only 32-bit libmali/EGL/GLES |
| Userspace | 32-bit armv7, softfp ABI, glibc of the firmware. The kernel is aarch64 4.4.84 |
| Root | [RootMyTV](https://rootmy.tv): telnet as root without login, [webOS Homebrew Channel](https://github.com/webosbrew/webos-homebrew-channel), developer mode for IPK installs |

## Build hosts

Builds ran on an arm64 Mac in Docker (colima, 12 CPUs, 24 GB RAM). Each engine has its own named volume, image and Dockerfile in its directory.

| Engine | Image base | Compiler |
|---|---|---|
| WPE (`buildroot/Dockerfile`) | Ubuntu 24.04 with buildroot prerequisites | buildroot-nc4 toolchain, `arm-webos-linux-gnueabi-gcc` 16.2.0 |
| cr120 (`cr120/Dockerfile`) | Ubuntu 24.04 arm64, qemu-user-static for arm32 build tools | clang/lld 18 (distribution), no Chromium-bundled clang |
| cr151 (`cr151/Dockerfile`) | Ubuntu arm64 | clang 23.1.6 from apt.llvm.org, rustc nightly 2026-06-16, node 24, ninja 1.12.1 |

## Engines and build systems

| Project | Version used | What was taken |
|---|---|---|
| [WPE WebKit](https://wpewebkit.org) | 2.52.6 (sha256 `b2bafef2…c858e`, pinned in `buildroot/build.sh`) | The engine. 2.52 is the last branch with the 32-bit JIT, which 2.54 removes |
| [openlgtv/buildroot-nc4](https://github.com/openlgtv/buildroot-nc4) | commit `322ff04e625a7927338c2ac5f3d02cd0511c9b90` | Toolchain, `webos_tv_defconfig` and the WPE packages |
| [kimjione1206/tv-wpe-build](https://github.com/kimjione1206/tv-wpe-build) | read 2026-11-09 | First proof that WPE builds for webOS with buildroot-nc4. Basis of WPE patches 0001-0004 and the libgcrypt and wpebackend-fdo patches |
| [webosose/chromium120](https://github.com/webosose/chromium120) | commit `e6a73fffdbe3bcc6f7fc33316c74adc6e7c01853` (Chromium 120.0.6099.269) | cr120 source tree, `git clone --depth 1` |
| [webosose/meta-webosose](https://github.com/webosose/meta-webosose) | read 2026-11-16 | The OE recipes (`webruntime*.bb`) that build chromium120. Used as the reference for GN args |
| [01org/ozone-wayland](https://github.com/01org/ozone-wayland) | as vendored in chromium120 | The `wayland_external` ozone backend that OSE uses |
| [sarahahzub/WebOS-Chromium](https://github.com/sarahahzub/WebOS-Chromium) | main after 1.0.0, commit `7265f39572b12546334c320eea4852dca1f44ff0` (Chromium 151.0.7922.108; was release 0.0.66, `1499d397`, until 2026-11-20) | cr151 itself. The NDL hardware video path (its patches 0023-0026 and `cnrun.c`), ported into cr120 |
| [webOS-ports/chromium151](https://github.com/webOS-ports/chromium151) | as pinned by WebOS-Chromium | Base tree of WebOS-Chromium (LuneOS, derived from OSE chromium120) |
| [webosbrew/webos-bridge-64to32](https://github.com/webosbrew/webos-bridge-64to32) | v0.0.8 + deten's 12 patches from [issue #1](https://github.com/webosbrew/webos-bridge-64to32/issues/1) | 64-bit EGL/GLES bridge for the frozen 64-bit path |
| [microsoft/mimalloc](https://github.com/microsoft/mimalloc) | v2.1.7 | Allocator preloaded into WPE's processes |
| [webosbrew/SDL-webOS](https://github.com/webosbrew/SDL-webOS) | 2.30.12 | Window and input for the WPE host |
| ChromeOS AFDO profile | `chromeos-chrome-arm-none-151-7922.56-1785723319-benchmark-151.0.7922.106-r1-redacted.afdo.xz` (6.4 MB, unpacked sha256 `d4e79e6c…bd3c97`), from `gs://chromeos-prebuilt/afdo-job/vetted/release/` | Sample profile for the AFDO build, 2026-11-27 (`cr151/afdo_ab.txt`) |
| Chromium Android arm32 PGO profile | `chrome-android32-main-1782755966-1961c5f9f820dc682ff75615a631f085003a8cca-67bd0dd250a1781c6e6ad77636a8709ded9a621c.profdata` (sha256 `911f00cd…087bd7`, 227 MB unpacked), from `gs://chromium-optimization-profiles/pgo_profiles/`, as pinned in `chrome/build/android-arm32.pgo.txt` | `pgo_data_path` in `cr151/args.delta.gn` since 2026-11-27 |
| Linux `tools/perf` | 4.4.302 (kernel.org tarball) | Static `perf` for the TV |
| Debian `libjavascriptcoregtk-bin` | 2.54.0 arm64 (trixie) | Reference 64-bit jsc for the 32-vs-64-bit JS comparison |
| Debian buster arm sysroot | debootstrap from archive.debian.org | Sysroot for cr120 (`cr120/sysroot.sh`) |

## Benchmark suites

They are not vendored. Clone them into `bench/suites/` and copy them to `/media/developer/bench/` on the TV.

| Suite | Repository | Ref |
|---|---|---|
| Speedometer 3.1 | [WebKit/Speedometer](https://github.com/WebKit/Speedometer) | branch `release/3.1`, commit `1386415be8fef2f6b6bbdbe1828872471c5d802a` |
| JetStream 3.0 | [WebKit/JetStream](https://github.com/WebKit/JetStream) | commit `06785cf861ac44855f168cbbe829278c2802e6de` |
| MotionMark 1.3.2 | [WebKit/MotionMark](https://github.com/WebKit/MotionMark) | tag `release/MotionMark1.3.2`, commit `0e740d50f2321d255f6176e2f57493574c735996` |

## Platform knowledge and prior art

| Project | What it taught |
|---|---|
| [mariotaku/ss4s](https://github.com/mariotaku/ss4s) (moonlight-tv, chiaki-lg) | NDL DirectMedia call sequence from a jailed homebrew app (`modules/webos/ndl`), and the Starfish (SMP) alternative |
| [webosbrew/webos-userland](https://github.com/webosbrew/webos-userland) | NDL API 2 structure layouts (`NDL_DIRECTMEDIA_DATA_INFO_T`) |
| punktfunk/client-webos (`docs/NOTES.md`) | NDL logging through `_PmLogMsgKV`/`PmLogString_` and other NDL gotchas |
| [xbmc/xbmc](https://github.com/xbmc/xbmc) (Kodi for webOS) | Hardware decode through Starfish media APIs from homebrew |
| [GLinnik21/plx-native](https://github.com/GLinnik21/plx-native) | Native media playback on webOS homebrew |
| [webosose/chromium84](https://github.com/webosose/chromium84) | Earlier OSE Chromium, compared for the neva media layer |
| [jsong1230/webosbrowser](https://github.com/jsong1230/webosbrowser), [atlet99/astra-webos-browser](https://github.com/atlet99/astra-webos-browser) | Other webOS browser attempts. Both wrap the TV's own engine, not a new one |
| [webosbrew/apps-repo](https://github.com/webosbrew/apps-repo) | Homebrew distribution and the request for a Chromium port |
| [ViieeS/mytvlauncher](https://github.com/ViieeS/mytvlauncher) | Telnet and IPK tooling for this TV, SDL-webOS remote and screensaver handling |
