# Input latency on heavy sites (2026-11-19 to 2026-11-20)

Question: why does Chromium TV (`com.viiees.chromiumtv`) answer the remote slowly on heavy sites, and what fixes it?
The owner scrolls with the Magic Remote wheel and moves the pointer. Keys are a secondary case.

## Summary

- **Wheel scrolling runs on the compositor thread**, even on Daily Mail, where the page's main thread is blocked for
  4–6 s at a time. A wheel notch reaches the screen in ~140–230 ms on Wikipedia and Daily Mail, and in 470–730 ms on
  reddit and YouTube.
- **The main cause of the slowness is the page's main thread, busy with site scripts.** It does not stop the scroll
  itself. It delays everything else: hover, keys, feed loading, and what the page draws after a scroll.
- **Browser flags change almost nothing.** Of the flags tried, only `--disable-smooth-scrolling` helped noticeably,
  and not on every site.
- **Correction (2026-11-22): the GPU was off.** The launcher turns the GPU off for good after one crash with the GPU
  on (`data/gpu.state`). It did so on 2026-11-21, and the wheel tables below look like the same software mode: notch
  147–224 ms, surface-manager 100+ ms per notch. With the GPU on, a Wikipedia notch costs a fraction of that, the
  compositor drops 0–4 % of frames, and a CDP scroll gesture is 0–3 % late. See "Late frames: an artifact" below.
- **The "~90 % late frames" is a metric artifact.** v4 reads it from evdev event timestamps that run 15–30 ms late.
- **autoconsent loads the main thread while the page scrolls.** rAF frames are 51 ms with it and 18 ms without it.

## What to fix (most useful first)

1. **`--disable-smooth-scrolling`: enabled in `cr151/package.sh` (2026-11-20).** The owner tried it with the remote
   wheel and kept it. The notch is faster on Wikipedia (196 → 142 ms), YouTube (730 → 556 ms) and Daily Mail
   (223 → 184 ms). No difference on reddit (474 → 539 ms, with 250–700 ms spread between runs). The cost: no scroll
   animation, the page jumps 120 px per notch.
2. **YouTube: the desktop site instead of the TV one.** With TV Tools' TV user agent, `youtube.com/tv` redirects to
   the desktop site (`?app=desktop`). Desktop YouTube is heavy: rAF frames of ~230–250 ms, hover ~400–800 ms per
   move. Try another user agent for youtube.com that keeps leanback (`/tv`). Not measured.
3. **Heavy scripts of single sites.** Daily Mail blocks the main thread for seconds, and uBO Lite in complete mode does
   not prevent it: the site injects its heavy obfuscated scripts at run time. Only site-specific blocking rules can
   help. That is work per site, not a system fix.
4. **Keep the GPU on.** One crash with the GPU on puts every later start into software mode, silently. That made
   scrolling several times slower. Find the crash (status 11 after 27 s on 2026-11-21), and check `gpu:` in
   `media.log` before any measurement.
5. **Stop autoconsent rescanning while the page scrolls.** Its CMP detection retries up to 20 times, each after
   500 ms and a DOM mutation. Scrolling mutates the DOM, so it reruns every rule's `querySelectorAll` during the scroll.

**No effect** (no visible difference on Wikipedia and reddit): `--num-raster-threads=2`,
`--disable-low-end-device-mode`, `--disable-gpu-rasterization`, raised thread priorities (variant `prio`), GPU out of
process (`--in-process-gpu` removed). Leave them as they are.

**uBO Lite** runs in complete mode on all sites (checked in the owner's profile). Turning uBO Lite off does not make
wheel scrolling faster. Hover on YouTube is faster without it (786 → 416 ms per move), but that is 2 runs per variant.
It needs a recheck.

## Method

- **Build.** The smooth-scrolling and hover series (`inputlat_wheel_smooth*.txt`, `inputlat_hover.txt`) ran on
  Chromium TV with patches 0100–0108, IPK sha256 `cc72d997…`. The first line of these files names the build. The
  earlier files ran on the same build or on the one before it, without 0108. Which one was not recorded. Owner's
  profile: TV Tools and uBO Lite (`filteringModeDetails` = complete for `all-urls`, 6 default rulesets).
- **Runs.** Every run is a fresh launch on the site. Variants are interleaved, 1–3 runs per variant. Flag variants go
  through `browser.flags`. Variants with no negating switch (`gpuproc`, `noppsite`) remove the switch from the
  installed `run.sh` for one launch (copy in `run.sh.ab`, restored after the launch). The owner allowed this.
- **Input.**
  - Wheel: `bench/evkeys` writes `REL_WHEEL` into `/dev/input/event3` ("LGE M-RCU"). 30 notches 80 ms apart in three
    bursts (12 down, 12 down, 6 up) with 1.5 s pauses. One notch is 120 px.
  - Hover: CDP `Input.dispatchMouseEvent`, 120 moves over a grid, 10 ms apart. The pointer does not pass through
    evdev: surface-manager sends the position only with the next wheel event.
  - Keys: arrows into `/dev/input/event10`.
- **Metrics.**
  - Chromium histograms: `EventLatency.GestureScrollUpdate.Wheel.TotalLatency2` (notch),
    `EventLatency.FirstGestureScrollUpdate.Wheel.TotalLatency2` (first notch of a burst),
    `Event.ScrollJank.DelayedFramesPercentage4.PerScroll` (late frames), `Renderer4.ScrollingThread.Wheel`
    (0 = scrolled on the compositor thread), `EventLatency.MouseMoved.TotalLatency` (hover).
  - From the page: an rAF log with `scrollY`, the time from a `wheel` event to the frame with the new offset, Long
    Animation Frames, Event Timing for `mouseover` and `keydown`.
  - CPU by chrome thread and process, and for the whole TV, over the input.
- **Tools.** `bench/inputlat.py run|show`, `bench/evkeys.c`. `bench/wheeltrace.py` tried to split the latency by stage
  through a trace. The trace is empty of those events: see `trace_wheel_wiki.json.gz`.

## Wheel

All series together (`inputlat.py show` over the wheel files below). "Notch" is the mean of
`GestureScrollUpdate.Wheel.TotalLatency2`. "Wheel → frame" is the p50 from a `wheel` event to the rAF frame with the
new `scrollY`, on the page clock.

| Site | Variant | Runs | Notch, ms | First notch, ms | Late frames, % | rAF frame, ms | Wheel → frame p50, ms |
|---|---|---|---|---|---|---|---|
| Wikipedia | base | 3 | 196 | 118 | 90 | 33 | 117 |
| Wikipedia | no smooth scrolling | 3 | 142 | 116 | 91 | 25 | 110 |
| reddit | base | 5 | 474 | 171 | 81 | 143 | 120 |
| reddit | no smooth scrolling | 3 | 539 | 138 | 86 | 163 | 135 |
| reddit | no uBO Lite | 2 | 347 | 129 | 84 | 178 | — |
| Daily Mail | base | 3 | 223 | 122 | 85 | 4649 | 3899 |
| Daily Mail | no smooth scrolling | 1 | 184 | 133 | 88 | 3938 | 5958 |
| YouTube, search | base | 2 | 730 | 328 | 74 | 228 | 439 |
| YouTube, search | no smooth scrolling | 2 | 556 | 396 | 73 | 253 | 362 |

Variants tried only on Wikipedia and reddit, 1–2 runs (`inputlat_wheel_ab1.txt`):

| Variant | Wikipedia notch, ms | reddit notch, ms |
|---|---|---|
| base (same series) | 168 | 631 |
| `--num-raster-threads=2` | 218 | — |
| `--disable-low-end-device-mode` | 224 | 298 |
| `--disable-gpu-rasterization` | 202 | 421 |
| thread priorities (`prio`) | 213 | 700 |
| GPU out of process (`gpuproc`) | 217 | — |

- On every site `Renderer4.ScrollingThread.Wheel` = 0: the compositor drives the scroll.
- **Daily Mail.** The rAF frame is 4–5 s, and the page sees the new offset after 4–6 s. The notch histogram still
  says ~200 ms: the screen scrolls, and the page scripts learn about it seconds later.
- **reddit.** The wheel reaches the page in batches: 10–17 `wheel` events for 30 notches. Chrome coalesces events
  while the main thread is busy.
- **Wikipedia.** Each burst of notches starts with ~1 s of 65–94 ms frames. The Long Animation Frames of these
  frames (50–400 ms) have no scripts, so this is rendering. After that, rAF frames come every ~40 ms while the
  page scrolls, and every 16–17 ms only when the scroll stops. (Software mode, see the correction above.)

### Late frames: an artifact, plus software mode (2026-11-21 to 2026-11-22)

Only `DelayedFramesPercentage4` (v4) showed the ~90 %. Legacy `DelayedFramesPercentage` and `MissedVsyncs` were 0.
Wikipedia, Chromium TV 1.0.0, interleaved runs.

**First series, GPU off without anyone noticing** (`inputlat_cdpwheel.txt`, `inputlat_cdpgesture.txt`, 3 runs each):

| Input | Scrolls per run | v4, % | Legacy, % | Compositor `WheelScroll` dropped, % | rAF dropped, % |
|---|---|---|---|---|---|
| evdev notches (`wiki-wheel`) | 2 | 90.5–91 | 0 | 44–45 | 74–77 |
| CDP `mouseWheel` notches (`wiki-cdpwheel`) | 14–18 | 0 | 0 | — | — |
| CDP `synthesizeScrollGesture` (`wiki-cdpgesture`) | 3 | 94 | 16–27 | 66 (1 run of 3) | 87 (1 run of 3) |

**Second series, GPU forced on** with `gpu=on` in `/tmp/com.viiees.chromiumtv/media.opts`
(`inputlat_gpu_ext.txt`, 3 runs per cell; `noext` drops autoconsent, `zeroext` drops all extensions):

| Input | Variant | v4, % | Legacy, % | Compositor dropped, % | rAF dropped, % | Notch `EventLatency`, ms | rAF frame, ms |
|---|---|---|---|---|---|---|---|
| evdev notches | base | 91 | 0 | — | — | 13 | 50.8 |
| evdev notches | no autoconsent | 91 | 0 | 3–4 | 4–4.5 | 13 | 17.8 |
| evdev notches | no extensions | 91 | 0 | 2 | 4–5 | 11–13 | 17.4 |
| CDP gesture | base | 1–3 | 1.5–3.5 | 0 | 43 (1 run) | — | — |
| CDP gesture | no autoconsent | 0.3–1 | 0–1.5 | 0–1 | 7.5–12.5 | 27–46 | — |
| CDP gesture | no extensions | 0–0.7 | 0–0.5 | 0 | 0–7.5 | 27–31 | — |

The Smoothness histograms do not reach the browser in every run, so some cells have fewer runs. One base wheel run
failed to open the page.

- **With the GPU on, scrolling is smooth.** The compositor drops 0–4 % of frames, and the gesture is 0–3 % late.
- **v4 on evdev notches is an artifact.** It stays at 91 % while almost no frame is dropped. The notch's
  `EventLatency` is 11–13 ms, less than one frame, against 27–46 ms for the gesture. So the evdev and Wayland event
  timestamps run 15–30 ms late, and v4 judges frames from them. Do not use v4 with evdev input on this TV.
- **CDP `mouseWheel` notches are no control.** They are never latched into one scroll: each notch is a scroll of one
  frame, and v4 is 0 for those by construction. Desktop Chrome on a Mac does the same (`bench/deskjank.py`).
- **autoconsent slows the page's frames while it scrolls.** With it, rAF frames are 51 ms on evdev notches and 43 % of
  them drop on the gesture. Long Animation Frames grow from 6 to 124 ms per notch. perf names the work:
  `SelectorQuery::ExecuteSearch` and `SelectorChecker::MatchSelector` take most of the renderer main thread
  (`bench/scrollperf.py`, `cr151/scrollperf/`).
- **Software mode** (GPU off): VizCompositorTh composites in Skia's software pipeline (`neon::lowp::*`), and
  surface-manager's CPU per scroll grows about 4 times.
- reddit is noisy: the base ranges from 226 to 631 ms across series. The differences between variants on reddit are
  smaller than this spread.

### autoconsent during a scroll (2026-11-22, GPU on)

autoconsent's `findCmp` retries up to 20 times when it finds no CMP, each after 500 ms and a DOM mutation, and every
retry reruns all rules' `querySelectorAll` (heuristics on every second one). A scroll mutates the DOM, so the
retries run during it. `acidle` is a test build of the shipped `lean-frames` add-on in which each retry first waits
for 1 s without `wheel`, `scroll` or `keydown` (`inputlat_acidle.txt`, 3 runs per cell, Wikipedia):

| Variant | rAF frame on notches, ms | LoAF per notch, ms | `wheel` events seen | rAF frame on the gesture, ms |
|---|---|---|---|---|
| shipped | 52.7 | 123 | 45/90 | 20–26 |
| `acidle` | 26.1 | 66 | 70/90 | 18.4–18.6 |
| no autoconsent | 17.7 | 8 | 89/90 | 17 |

The rest of the cost in `acidle` falls in the 1.5 s pauses between bursts: a retry starts there, and the next burst
meets it. Whether `acidle` still rejects: `bench/results/consent/shipped_*.txt`.

### Smooth scrolling again, with the GPU on (2026-11-22)

`smooth` removes `--disable-smooth-scrolling` from the installed `run.sh` for one launch (`inputlat_smooth_gpu.txt`,
3 runs per cell). The notch columns come from evdev timestamps, which run late, so compare them only between
variants:

| Site | Variant | Notch, ms | First notch, ms | rAF frame, ms | Wheel → frame p50, ms |
|---|---|---|---|---|---|
| Wikipedia | no smooth (shipped) | 13 | 24 | 54.5 | 89 |
| Wikipedia | smooth | 13 | 21 | 53.7 | 85 |
| reddit | no smooth (shipped) | 30 | 18 | 71.0 | 123 |
| reddit | smooth | 74 | 193 | 94.5 | 137 |
| YouTube, search | no smooth (shipped) | 16 | 20 | 173.8 | 156 |
| YouTube, search | smooth | 14 | 19 | 233.8 | 190 |

Keep `--disable-smooth-scrolling`: no difference on Wikipedia, better on reddit and YouTube.

## Hover

A grid of 120 pointer moves. "Move" is the mean of `EventLatency.MouseMoved.TotalLatency`. "mouseover" is the mean of
Event Timing entries for `mouseover` of 16 ms and more.

| Site | Variant | Runs | Move, ms | mouseover ≥16 ms | mouseover, ms |
|---|---|---|---|---|---|
| YouTube, search | base | 2 | 786 | 42 | 286 |
| YouTube, search | no uBO Lite | 2 | 416 | 38 | 140 |
| reddit | base | 1 | 234 | 42 | 40 |
| reddit | no uBO Lite | 1 | 234 | 46 | 53 |

Daily Mail is left out: 1 of 120 moves reached the page, the main thread was busy for the whole run.

## Keys (secondary case)

| Site | Variant | Runs | Keys ≥16 ms | Duration, ms | Input delay, ms | EventLatency, ms |
|---|---|---|---|---|---|---|
| YouTube | base | 2 | 18/56 | 88 | 13 | 236 |
| YouTube | no spatnav | 2 | 5/56 | 114 | 104 | — |
| YouTube | no uBO Lite | 1 | 8/28 | 158 | 1 | 393 |
| reddit | base | 2 | 60/60 | 341 | 221 | 406 |
| reddit | no spatnav | 1 | 27/30 | 510 | 387 | 581 |
| reddit | no uBO Lite | 1 | 31/30 | 567 | 317 | 723 |
| Daily Mail | no uBO Lite | 2 | 0/60 | — | — | — |

- Spatial navigation (`--enable-spatial-navigation`) runs on every arrow on every site: no site cancels the arrows.
  On YouTube there are three times fewer slow keys without it. The owner rarely uses the arrows, so it stays.
- Google Maps is left out of the table: without spatnav the arrows move the caret in the search field, so the
  scenario is not comparable.
- Key latency on heavy sites is mostly waiting for the main thread: reddit ~440 ms per arrow, Daily Mail ~1440 ms
  (`inputlat_probe*.txt`).

## Environment and limits

- The TV's load average of ~13.7 comes from threads in state D, not from CPU. The CPU is ~91 % idle.
- Background processes on the TV during the runs: the preloaded YouTube app (cobalt, 6–10 % of a core), nn-proxy,
  surface-manager, memchute, and the renice loop in `run.sh` (~3 % of a core).
- The kernel exposes no cpufreq: frequency and governor are not visible.
- Few runs: 1–3 per variant. Results with a difference smaller than the spread (reddit, hover without uBO Lite) are
  marked as needing a recheck.
- **Failed runs.** 11 of 24 runs in the last series failed: 10–20 s after load the tab has no URL (url ""), only on
  reddit and Daily Mail. The cause is not known, possibly a renderer crash. dmesg shows no OOM. These runs are not in
  the tables.
- After the last Daily Mail run the browser did not exit within 20 s of `closeByAppId`, even with patch 0108. It had
  to be ended with `kill -9`.

## Raw files

| File | Contents |
|---|---|
| `inputlat_probe.txt`, `inputlat_probe_ytredirect.txt` | first key runs, the `youtube.com/tv` redirect to desktop |
| `inputlat_spatnav.txt`, `inputlat_ab_spatnav_ubol.txt` | keys: base, no spatnav, no uBO Lite |
| `inputlat_wheel_base.txt` | wheel, base on 4 sites |
| `inputlat_wheel_ab1.txt` | wheel: raster2, nolowend, nogpuraster, prio, gpuproc, noubol |
| `inputlat_wheel_smooth.txt`, `inputlat_wheel_smooth2.txt`, `inputlat_wheel_smooth3.txt` | wheel: base and no smooth scrolling |
| `inputlat_hover.txt` | hover: base and no uBO Lite |
| `inputlat_cdpwheel.txt`, `inputlat_cdpgesture.txt` | late frames check: evdev against CDP notches and a CDP scroll gesture (GPU off) |
| `inputlat_smooth_gpu.txt` | smooth scrolling on and off with the GPU on |
| `inputlat_acidle.txt` | autoconsent whose retries wait for an idle user, against shipped and none |
| `inputlat_gpu_ext.txt` | the same with the GPU on, with and without autoconsent and all extensions |
| `scrollperf/*.txt.gz` | system-wide perf during a wheel scroll (`bench/scrollperf.py report <file>`): base, `noext`, `zeroext`, `onlytvt` with the GPU off, `gpu_base` with the GPU on |
| `trace_wheel_wiki.json.gz` | wheel trace on Wikipedia: it has no `cc` or `viz` events |

The tables come from `TV_HOST=x bench/inputlat.py show <files>`. `show` does not need the TV.
