# WPE WebKit 2.52.6 for webOS: frozen

The status covers `buildroot/` (engine build), `host/` (the SDL/Wayland app that embeds WPE) and `mimalloc/`.

**Why it is frozen.**
- It has the fastest JavaScript of all engines tried: Speedometer 3.1 0.80-0.83, micro ~230 ms.
- It loses where users notice:
  - rAF scrolling runs at 26-28 fps;
  - after load the main thread stays busy for 5.3 s, against 1.3 s in the stock browser;
  - video is software only, ~14 fps at H.264 1080p30;
  - there is no EME.
- Chromium (cr120, then cr151) gets hardware video through NDL and 60 fps scrolling. See [docs/BENCHMARKS.md](../docs/BENCHMARKS.md).

## Build

```bash
WEBKIT_MCPU=cortex-a55 buildroot/build.sh      # buildroot-nc4 @322ff04e in docker volume wpe-br
```

- `build.sh` pins WebKit to 2.52.6 and applies `patches/` to the build.
- It enables the softfp JIT (DFG, no FTL, no WebAssembly).
- With `WEBKIT_MCPU` it compiles WebKit for the C1's real cores. Buildroot-nc4 defaults to cortex-a9.
- CMakeCache keeps CFLAGS between runs. When you switch `WEBKIT_MCPU`, run `make wpewebkit-reconfigure` with the value set.
- Host and package:
  - `host/bundle.sh` runs in the container and collects the app.
  - `host/make_ipk.py` builds the IPK and needs `$MYTVLAUNCHER`.
  - `host/deploy_host.sh <tv>` swaps only the host binary and needs `$SDL_PKG`.

## Patches (`patches/wpewebkit`)

| Patch | What |
|---|---|
| 0001-0004, 0007 | webOS environment: MADV_DONTDUMP, roundeven, Skia softfp ABI, exec path and PSON from env |
| 0006, 0009 | JIT on a softfp userspace: JIT operations use the VFP calling convention. DFG math folding keeps it |
| 0008 | Build fix: WasmOrigin needs WebAssembly |
| 0010-0012 | Three bugs in the ARMv7 YARR RegExp JIT. Fixed, regexp-octane 4.5 -> 24.1 points. The runtime switch is `JSC_useRegExpJIT=true` |
| 0013 | bmalloc SystemHeap aligns to 16 on Linux (an offset word before the block). Fixes SIGBUS with `-mcpu=cortex-a55` |
| 0014 | Sticky elements no longer force relayout on every scroll. Compositing geometry is updated instead |
| 0015 | CSS selector JIT on ARMv7 (Thumb-2 + hardware divide). Style time 33% -> 24% of the wiki load. Generator: `build/cssjit_armv7.py` |

The A/B for each patch is in `build/ab-*.sh` and `build/*.log` and in `bench/results/*.jsonl`.

## Measured effect of the main levers

- `-mcpu=cortex-a55` needs patch 0013. Without it, SIGBUS. It also enables hardware divide, which the CSS JIT requires. The first version of 0013 (aligned_alloc) cost 15% and was replaced by the offset-word version. Numbers: `build/ab-a55.log` and `build/ab-v2.log`.
- **CSS JIT (0015):** Speedometer 0.729 -> 0.738.
- **mimalloc preload** (host default, `env=LD_PRELOAD=` turns it off):
  - Speedometer 0.741 -> 0.825;
  - wiki load 4-9% faster;
  - RSS +5..12% on pages.

## Where to resume

- **Hardware video.** Use the NDL path from cr120/cr151 (`cr120/launcher/cr120run.c` and `cr120/extra/content/renderer/media/cn_ndl_renderer.cc`): a GStreamer sink or a MediaPlayerPrivate that feeds NDL. Today WPE bundles its own GStreamer, which decodes in software.
- **Post-load busy time.** WPE fires `load` before the first full style and layout pass, Chrome after it. Per perf, the remaining hot spots are allocation (~11%), ElementRuleCollector and Style::Invalidator.
- **64-bit build.** It gives about 1.6x JS (see `buildroot64/STATUS.md`). It needs a display bridge.
- **WebKit 2.54** removes the JIT for every 32-bit target. A 32-bit WPE stays on 2.52.x.
