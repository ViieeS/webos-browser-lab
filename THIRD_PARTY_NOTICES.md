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

Shipped in the cr151 IPK built by `cr151/package.sh`, not stored in the repository:

| IPK path | Origin | License |
|---|---|---|
| `browser/ext/autoconsent/` | [DuckDuckGo autoconsent](https://github.com/duckduckgo/autoconsent) 18.9.0, npm package `@duckduckgo/autoconsent` (`autoconsent-18.9.0.tgz`, sha256 `04a49d0c…`), its prebuilt `dist/addon-mv3`. Changed by `cr151/autoconsent.sh` (lean-frames): logging off; rules and config cached in memory; no status icon or popup mutation observer; `rules.json` dropped; content script limited to main frames and rule-matched subframes | MPL-2.0, Duck Duck Go, Inc. and contributors. The license text ships in the folder (`LICENSE`). The source is at the origin link, and the changes are the `perl` and `autoconsent_frames.py` steps in `cr151/autoconsent.sh` |
| `browser/ext/ubol/` | [uBlock Origin Lite](https://github.com/uBlockOrigin/uBOL-home) 2026.1116.1650, official release `uBOLite_2026.1116.1650.chromium.zip`, unpacked. One change: `js/mode-manager.js` defaults to complete filtering mode instead of optimal (`package.sh`) | GPL-3.0, Raymond Hill and contributors. The license text ships in the folder (`LICENSE.txt`). The source is at the origin link, and the change is the `sed` line in `package.sh` |

Not included and fetched separately:
- benchmark suites (Speedometer, JetStream, MotionMark: BSD-2-Clause, Apple and the WebKit contributors);
- upstream source trees;
- LG libraries from the TV. The LG libraries are proprietary and are never redistributed here.
