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

## Verdict

- The build flags help everywhere by 14-25 %, but do not fix the UI. One key in the omnibox still takes about
  160 ms to reach the screen. One Down press in a page takes about 160 ms. Judgment, not measured here: on a
  desktop the same metrics are tens of milliseconds.
- About 60 ms of the omnibox time is PaintToPresent: raster, GPU and display after Views has painted. Trimming UI
  features would mostly shorten ToPaint (about 70 ms). It would not shorten PaintToPresent.
- So the flags alone are not enough. Before picking a ROADMAP item 2 option, the next cheap step is to split the
  present path. These are both Chromium's own tools, not tried yet:
  - a Perfetto trace with the `latencyInfo`/`input` categories, read through `chrome_event_latencies`, gives the
    stages per key;
  - an A/B run of `uilat.py` with `--disable-smooth-scrolling` (keyscroll) and with software compositing.
- A camera measurement (phone slow motion) is not needed to confirm the slowness, because Chromium's own numbers
  already show it. It would add the input path that the metrics leave out.
