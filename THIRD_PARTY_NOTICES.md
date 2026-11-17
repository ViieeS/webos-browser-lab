# Third-party notices

The MIT license in [LICENSE](LICENSE) covers this repository's own scripts, documents, test pages and launcher code.
The material below keeps its original license.

| Path | Origin | License |
|---|---|---|
| `buildroot/patches/wpewebkit/*.patch` | Patches to [WebKit](https://github.com/WebKit/WebKit) (WPE port) | Follow the files they patch: BSD-2-Clause or LGPL-2.1 (WebKit's own terms) |
| `buildroot/patches/wpewebkit/0001-0004`, `buildroot/patches/{libgcrypt,wpebackend-fdo}` | Derived from [kimjione1206/tv-wpe-build](https://github.com/kimjione1206/tv-wpe-build) | Same as the patched projects |
| `cr120/patches/*.patch`, `cr151/patches/*.patch` | Patches to Chromium ([webosose/chromium120](https://github.com/webosose/chromium120), [WebOS-Chromium](https://github.com/sarahahzub/WebOS-Chromium)) | BSD-3-Clause (The Chromium Authors) |
| `cr120/patches/0014-*`, `cr120/patches/0015-*`, `cr120/extra/content/renderer/media/cn_ndl_renderer.*`, `cr120/extra/ozone/wayland/foreign_window/cn_video_export.*` | Ported from [sarahahzub/WebOS-Chromium](https://github.com/sarahahzub/WebOS-Chromium) (its patches 0023-0026) | BSD-3-Clause, Copyright 2026 The WebOS Chromium Authors |
| `cr120/launcher/cr120run.c` | Protocol and NDL call sequence follow WebOS-Chromium's `source/package/launcher/cnrun.c` | This repository's code under MIT. The parts that follow cnrun.c also carry BSD-3-Clause, Copyright 2026 The WebOS Chromium Authors |
| `bridge64/patches-zip/` | Patch series by deten for [webosbrew/webos-bridge-64to32](https://github.com/webosbrew/webos-bridge-64to32), attached to its [issue #1](https://github.com/webosbrew/webos-bridge-64to32/issues/1) | GPL-3.0, like the bridge |
| `bench/pages/wiki/` | Snapshot of [en.wikipedia.org/wiki/Television](https://en.wikipedia.org/wiki/Television) with its styles and images, used as a test page | Text CC BY-SA 4.0, Wikipedia contributors. Images under the licenses on their Wikimedia Commons pages. Wikipedia and Wikimedia marks belong to the Wikimedia Foundation |
| `bench/tvtelnet.py` | From [ViieeS/mytvlauncher](https://github.com/ViieeS/mytvlauncher) | MIT |

Not included and fetched separately:
- benchmark suites (Speedometer, JetStream, MotionMark: BSD-2-Clause, Apple and the WebKit contributors);
- upstream source trees;
- LG libraries from the TV. The LG libraries are proprietary and are never redistributed here.
