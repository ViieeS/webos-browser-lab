# 64-bit path (aarch64 WebKit on a 32-bit webOS userspace): frozen

The status covers `buildroot64/` (aarch64 buildroot + WPE, docker volume `wpe-br64`) and `bridge64/`. The bridge is [webosbrew/webos-bridge-64to32](https://github.com/webosbrew/webos-bridge-64to32) v0.0.8 plus a fork's patch series in `bridge64/patches-zip`.

**What works.**
- The C1 kernel is aarch64. A 64-bit binary with its own `ld-linux-aarch64.so.1` and libraries runs on the TV.
- On 28 JetStream-lite tests the same WebKit 2.52.6 does better in 64-bit than in our 32-bit build:
  - geomean 1.62x faster;
  - median peak RSS 90 MB against 120 MB.

  Raw data: `build/jsall*.txt`.

**Why it is frozen.**
- Mali EGL/GLES and LG's media stack (NDL, StarfishMediaAPIs) exist only as 32-bit libraries on the TV.
- So a 64-bit browser needs one of two things for display:
  - the 64to32 bridge, which forwards every GL call over shared memory to a 32-bit proxy;
  - CPU rendering (llvmpipe).
- Hardware video would also need a 32-bit helper process.
- Chromium in 32-bit, with NDL video, already met the goal.

**Where to resume.**
- The bridge build recipe: [docs/FINDINGS.md](../docs/FINDINGS.md).
- `buildroot64/run64.sh` starts the 64-bit WPE on the TV. It binds the inspector to `$DEVTOOLS_ADDR`, 127.0.0.1 by default.
