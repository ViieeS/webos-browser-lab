# Browser UI latency: own build against 0.0.66 (2026-11-17)

ROADMAP item 2. The owner finds the Chrome UI slow with the remote. Question: do the build flags of the own speed
build fix it, or is one of the item 2 options needed?

Only Chromium's own metrics are used, no own heuristics.

## Method

- **Builds.** `com.viiees.cr151` (own speed build) and `org.nativechromium.browser` (release 0.0.66). Both ran with
  `--remote-debugging-port=9225` in browser.flags during the runs.
- **Input.** `bench/evkeys` writes key events into `/dev/input/event10` ("LGE Network Input"). The compositor reads
  this node and passes the keys over Wayland, the same way as remote keys. Keys are 300 ms apart.
  `/dev/input/event1` ("LGE RCU") does not work: the compositor does not open it.
- **Metrics.** `bench/uilat.py` reads `Browser.getHistograms` over CDP, through a temporary relay. It reads a delta
  around each scenario.
  - Renderer histograms (`EventLatency.*`) reach the browser process only after a child fetch. The script opens
    `chrome://histograms` in a background tab before each read.
- **Runs.** Every run is a fresh launch on the local Wikipedia "Television" page. Builds were interleaved,
  3 rounds. Raw output: `uilat_cr151.txt`. The table comes from `bench/uilat_summary.py uilat_cr151.txt`.

| Scenario | Keys | Metric |
|---|---|---|
| omnibox | F6, then "wikipedia", Ctrl+A, Backspace, 3 times (27 characters per run) | `Omnibox.CharTypedToRepaintLatency` and its parts, `Omnibox.Views.PopupFirstPaint` |
| tabs | Ctrl+T once, then Ctrl+Tab × 20 | `Browser.Tabs.TotalSwitchDuration3` |
| keyscroll | Down × 20 in the page | `EventLatency.KeyPressed.TotalLatency` |
| keyfocus | Tab × 20 in the page (focus moves from link to link) | `EventLatency.KeyPressed.TotalLatency` |
| startup | the launch itself (12 per build) | `Startup.BrowserWindowDisplay`, `Startup.BrowserWindow.FirstPaint`, `Startup.FirstWebContents.NonEmptyPaint3` |

## Results

The mean is event-weighted over all runs. "runs" is the range of per-run means. "p50" is the range of per-run
median buckets (lower bounds; Chromium buckets are exponential).

| Metric | Scenario | Own build | 0.0.66 | Change of the mean |
|---|---|---|---|---|
| Omnibox.CharTypedToRepaintLatency | omnibox | 158 ms (runs 150-168, p50 135-160, n=81) | 190 ms (runs 187-194, p50 160-190, n=81) | -17 % |
| … .ToPaint (key to paint) | omnibox | 72 ms (runs 67-79) | 87 ms (runs 78-94) | -17 % |
| … .PaintToPresent (paint to screen) | omnibox | 62 ms (runs 61-64) | 74 ms (runs 72-79) | -16 % |
| Omnibox.Views.PopupFirstPaint | omnibox | 138 ms (n=9) | 174 ms (n=9) | -21 % |
| Browser.Tabs.TotalSwitchDuration3 | tabs | 113 ms (runs 112-114, n=60) | 131 ms (runs 125-140, n=60) | -14 % |
| EventLatency.KeyPressed.TotalLatency | keyscroll | 162 ms (runs 158-164, p50 147, n=60) | 215 ms (runs 214-217, p50 197, n=60) | -25 % |
| EventLatency.KeyPressed.TotalLatency | keyfocus | p50 52-61 ms, mean 238 ms (n=59) | p50 61-170 ms, mean 444 ms (n=56) | median -15 % or more |
| Startup.BrowserWindowDisplay | startup | 967 ms (runs 798-1749) | 999 ms (runs 855-1242) | within noise |
| Startup.BrowserWindow.FirstPaint | startup | 1313 ms (runs 1066-2062) | 1379 ms (runs 1203-1678) | within noise |
| Startup.FirstWebContents.NonEmptyPaint3 | startup | 2518 ms (runs 1876-5056) | 3402 ms (runs 2156-8497) | outliers in both |

- keyfocus means are dominated by a few very slow presses (one 0.0.66 run has a mean of 968 ms at a median of 170 ms). Compare the medians.
- Startup is counted from the creation of the chrome process. The SAM launch, the launcher and the GPU probe before
  it are not included.

## Caveats

- The metrics start at Chromium's timestamp of the key event. They do not include the path remote → LG input →
  compositor → Wayland. `Event.Latency.OS2.KEY_PRESSED` is always 0 here, so that part is not visible to Chromium.
- Omnibox suggestions came from Google, as for a person typing (no login). `CharTypedToRepaintLatency` measures the
  edit's repaint, not the suggestion fetch.
- cr151 renders at device scale 1.5. The UI is drawn at 1920x1080 physical pixels.
- crossbench and the typing-input-latency web test were not tried. Whether they run on the TV without a WebDriver
  was not checked.

## Stage split (trace) and A/B (2026-11-17, own build)

Traces: `bench/uilat.py trace <tag> <scenario> <out.json>` (CDP Tracing, JSON). `bench/uilat_trace.py` prints
Chromium's own stages of `EventLatency` and `PipelineReporter`. The traces (~200 MB) are not versioned
(`cr151/traces/`). Tracing adds overhead, so the trace numbers show where time goes, the histograms show how much.

**Down in a page (keyscroll).** EventLatency median 170 ms, of it `RendererMainProcessing` 130 ms. Everything
after the renderer (submit, draw, swap, present) is about 16 ms. With `blink` and `toplevel` categories, the renderer
main thread spends 219 ms per key inside `EventDispatch`, with about 3750 `Document::UpdateStyleAndLayout` calls
per key and almost no real layout. The cause is `--enable-spatial-navigation` from their run.sh. On every arrow,
spatial navigation walks the candidates of the page (`SpatialNavigationController`, `DocumentUpdateReason::
kSpatialNavigation`), and the Wikipedia page has thousands of them. `--blink-settings=spatialNavigationEnabled=false`
in browser.flags turns it off: main thread 2.3 ms per key, EventLatency 39 ms.

**Omnibox.** The frame pipeline is not the problem: browser `PipelineReporter` median 20 ms per frame. The browser
main thread is busy about 215 ms per typed character under the trace. The time goes to Views layout
(`View::LayoutImmediately`, about 10 000 calls in 27 characters), Views paint and autocomplete result updates
(`AutocompleteController::UpdateResult` → `OmniboxController::OnResultChanged` → a popup relayout). These sums
overlap, so they are not added up.

**A/B with histograms.** `uilat.py -b cr151own,cr151own+nospatnav,cr151own+nogpu 2 ...`, interleaved. Raw:
`uilat_ab.txt`. The run was stopped before the last tabs round, because the owner needed the TV.

| Metric | Scenario | Own build | + spatial navigation off | + `--disable-gpu` |
|---|---|---|---|---|
| EventLatency.KeyPressed.TotalLatency | keyscroll (Down) | 162 ms (p50 147) | **36 ms** (p50 34) | 258 ms (p50 228) |
| EventLatency.KeyPressed.TotalLatency | keyfocus (Tab) | 192 ms (p50 61) | **91 ms** (p50 45) | 342 ms (p50 170-228) |
| Omnibox.CharTypedToRepaintLatency | omnibox | 161 ms | 167 ms | 230 ms |
| … .ToPaint | omnibox | 78 ms | 85 ms | 68 ms |
| … .PaintToPresent | omnibox | 58 ms | 56 ms | 150 ms |
| Browser.Tabs.TotalSwitchDuration3 | tabs | 116 ms (1 run) | 114 ms (1 run) | 265 ms (1 run) |

- Spatial navigation costs 75-80 % of a Down press in a page, and half of a Tab press. It does not touch the browser UI.
- Software rendering is worse everywhere. The GPU path helps, it is not the bottleneck.
- The omnibox does not change with either flag. Its cost is browser main-thread work in Views and autocomplete.

## Verdict

- The build flags help everywhere by 14-25 %, but do not fix the UI. One key in the omnibox still takes about
  160 ms to reach the screen. One Down press in a page takes about 160 ms. Judgment, not measured here: on a
  desktop the same metrics are tens of milliseconds.
- About 60 ms of the omnibox time is PaintToPresent: raster, GPU and display after Views has painted. Trimming UI
  features would mostly shorten ToPaint (about 70 ms). It would not shorten PaintToPresent.
- So the flags alone are not enough. The stage split (above) names two separate causes:
  1. **In pages: spatial navigation.** It is why the remote's arrows move between links, so turning it off is a
     trade-off, not a fix: arrows would only scroll. Options:
     - the owner's choice, today: `--blink-settings=spatialNavigationEnabled=false` in browser.flags, if the Magic
       Remote pointer is enough for links;
     - a Blink patch that stops the per-candidate style and layout update in the candidate walk (with an upstream
       bug), which keeps arrow navigation.
  2. **In the omnibox and tab strip: browser main-thread work** in Views layout, paint and autocomplete. This is the
     "trim the UI" option of ROADMAP item 2 (fewer suggestion sources and popup rows), or a lighter own UI. Not GPU,
     not the build flags.
- `--disable-smooth-scrolling` was planned, but not run: the stage split showed that scrolling itself is about 16 ms
  after the renderer, so smooth scrolling is not the cause.
- A camera measurement (phone slow motion) is not needed to confirm the slowness, because Chromium's own numbers
  already show it. It would add the input path that the metrics leave out.

## Patch 0103: spatial navigation without a layout update per element (2026-11-18)

`patches/0103-spatnav-one-layout-update-per-walk.patch`, installed as dev app `com.viiees.cr151p` next to
`com.viiees.cr151` (the same build without it), measured interleaved.

**Cause, from the code.** `SpatialNavigationController::FindNextCandidateInContainer()` calls `IsValidCandidate()` on
every element of the page. It ends in `IsKeyboardFocusableSlow()` with the default `UpdateBehavior::kStyleAndLayout`,
and for non-links `CanBeKeyboardFocusableScroller()` calls `Document::UpdateStyleAndLayoutForNode()`. That is the
~3 750 `Document::UpdateStyleAndLayout` calls per key in the trace.

**Upstream.** `spatial_navigation_controller.cc` and `element.cc` in Chromium main, read on 2026-11-18, make the same
calls. No upstream fix exists to backport. The git log pages of googlesource need a login, so there is no CL link.

**First version, no effect.** It switched to the cheap path only when the document had no locked display lock. The
Wikipedia page has 54 (sections with `content-visibility: auto`), so it always took the old path: 166 → 164 ms.
A trace event in the walk showed this (`fast: false, locked: 54`).

**Second version, the patch now.** One update before the walk. For each locked display lock, the first element under
it keeps the forced update. All other elements are checked with `kNoneForFocusManagement`. If a forced update leaves
the document dirty, the rest of the walk goes back to the old path. The trace event
`blink / SpatialNavigation::CandidateWalk` reports: 11 672 elements walked, 54 forced updates, document stayed clean,
`Document::UpdateStyleAndLayout` 79 553 → 1 173 calls in 20 keys. Renderer main thread per Down: 219 → 79 ms (traced).

**Correctness** (`uilat.py focus`, raw: `spatnav_focus.txt`): the same keys on three pages, focused element after each
key, both builds.

| Page | Keys | Same focused element |
|---|---|---|
| `bench/pages/spatnav.html` (link grid, scroll container, form, `content-visibility` section) | 20 | 20 of 20 |
| local Wikipedia "Television" | 20 | 20 of 20 |
| news.ycombinator.com (live) | 12 | 10 of 12: steps 5 and 6 swapped two stories. Both builds moved one row down each time, the live ranking changed between the loads (judgment) |

**Latency** (`uilat.py -b cr151own,cr151p 3 keyscroll keyfocus`, raw: `uilat_0103.txt`):

| Metric | Scenario | Without 0103 | With 0103 | Spatial navigation off (reference) |
|---|---|---|---|---|
| EventLatency.KeyPressed.TotalLatency | keyscroll (Down) | 167 ms (p50 147-170) | **115 ms** (p50 109) | 36 ms |
| EventLatency.KeyPressed.TotalLatency | keyfocus (Tab) | 210 ms (p50 52-70) | 191 ms (p50 52-61) | 91 ms |

- Down in a page: -31 %, arrows still move between links.
- Tab barely changes. Sequential focus navigation does not use this walk.
- The rest, about 80 ms over the no-spatnav level, is the walk itself: 11 672 elements, a focusability check each and
  a rectangle for every candidate. Making it shorter means skipping parts of the page, for example offscreen locked
  sections. That changes which elements are candidates, so it is a separate decision.

## UI font (2026-11-18)

Not a latency item, but the owner saw it in the omnibox. Every family resolved to LG Display-Regular with full hinting.
Patch-free fix: our `fonts.conf` plus `FONTCONFIG_FILE` in run.sh (`package.sh`). Before and after:
`cap_font_omnibox_before.png` / `cap_font_omnibox_after.png` (Droid Sans, round dots, even spacing) and
`cap_font_page_before.png` / `cap_font_page_after.png` (page text in Droid Sans, bold now bold). Details in FINDINGS.
The fix is in `com.viiees.cr151p` only. `com.viiees.cr151` stays as built for A/B runs against the old state.
Omnibox latency runs after this point use the fixed font.
