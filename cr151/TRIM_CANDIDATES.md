# What else to switch off in Chromium 151 for the TV

Analysis only (2026-11-19). Nothing here is applied or measured on the TV yet. Every name below was checked in the
Chromium 151.0.7922.108 tree that `cr151/build.sh` builds (`out/tv`), unless the row says otherwise. GN rows were
checked with `gn gen` on a copy of `out/tv/args.gn` with the arg appended (generation only, nothing was compiled).

"Gain" is an estimate unless it cites a source. Sources are published numbers from other platforms, not from this TV.

## Measure these first

1. **`--disable-field-trial-config`.** Our build applies Chromium's whole field trial testing config at every start.
   That is 663 studies for Linux, which turn on 753 features that are off by default in M151: Glic, AutoSpeculationRules,
   DsePreload2, NewTabPageTriggerForPrefetch, HistoryEmbeddings, AnnotatedPageContentExtraction, ContentAnnotator,
   V8Flag_verify_bytecode_light, V8Flag_zero_unused_memory and more. It is one switch, needs no rebuild, and nobody
   chose these features for a TV. See "Field trial testing config" below.
2. **Preloading off:** the `net.network_prediction_options` pref plus four features that are on by default. With one
   renderer for all tabs, every prerendered or prefetched page lives in the same process as the tabs the user sees.
3. **Memory saver on** (`performance_tuning.high_efficiency_mode.state = 2`). This is the only lever here that can move
   the 15–19 heavy-tab ceiling. M151 has no Linux memory-pressure evaluator, so Chrome never discards tabs on its own on
   this TV. Memory saver's timer discards are the only discards it does.
4. **neva memory switches** that LG's web app manager passes on TVs, and that are live in our build:
   `--skia-resource-cache-limit-mb`, `--decoded-image-working-set-budget-mb`, `--enable-aggressive-release-policy`.
5. **One GN rebuild with the args that pass `gn gen`.** Expect little: together they remove 66 of 18 386 targets in
   chrome's dependency tree. Do it only if a rebuild happens anyway.

How to check what the field-trial switch changes: `chrome://version` lists the active variations, and
`chrome://version/?show-variations-cmd` prints them as `--force-fieldtrials` / `--enable-features`. Compare the list
before and after.

Prefs can be seeded the way run.sh already seeds `bookmark_bar` into `Default/Preferences`, or set once for a test
with `chrome.settingsPrivate.setPref` over CDP (FINDINGS.md, "Operating notes").

All feature additions must go into run.sh's single `--disable-features` / `--enable-features` lists. package.sh
already appends the omnibox trim there. A second `--disable-features` switch replaces the whole first list.

## Candidates, sorted by expected gain

| # | What to change (exact) | Kind | What the TV loses, and why it does not need it | Expected gain | Risk | In our build now? |
|---|---|---|---|---|---|---|
| 1 | `--disable-field-trial-config` (GN form: `disable_fieldtrial_testing_config = true`, gn gen passes) | switch | 753 experimental features: Gemini/Glic, AI page-content extraction, auto speculation rules, prerender warm-ups, V8 and PartitionAlloc experiments. They are Google's test arms, not product defaults | Unknown sign, possibly the largest single change. Estimate. ungoogled-chromium, Cromite and Thorium all set the GN form ([ungoogled flags.gn](https://github.com/ungoogled-software/ungoogled-chromium/blob/master/flags.gn), [Cromite gn_args](https://github.com/uazo/cromite/blob/master/build/cromite.gn_args), [Thorium args.gn](https://github.com/Alex313031/thorium/blob/main/args.gn)) | Some of the 753 help memory (Canvas2DHibernation, KillSpareRenderOnMemoryPressure, WebGLDiscardBackBuffer, V8MemoryReducerDelay). Re-enable those one by one if the A/B shows a loss. The forced omnibox trial still works, because `--force-fieldtrials` is separate | No. `--disable-background-networking` does not cover it: the config is compiled in, not downloaded |
| 2 | Pref `net.network_prediction_options = 2` (`kDisabled` in `chrome/browser/preloading/preloading_prefs.h`) plus `--disable-features=SearchPrefetchServicePrefetching,NavigationPredictor,PreconnectToSearch,LoadingPredictorUseOptimizationGuide` | pref + features | Prerender and prefetch of omnibox, search and link targets, and preconnects. On a TV with a slow remote these predictions rarely pay back, and a prerendered page costs a whole page of memory in the one shared renderer | Estimate: one prerendered page less (tens of MB) during omnibox use, less background network and CPU. Precedent: Cromite [Disable-all-predictors-code](https://github.com/uazo/cromite/blob/master/build/patches/Disable-all-predictors-code.patch) | Navigation from the omnibox can be slower by one connection setup. No site breakage | No. The omnibox trim only removed `PreconnectNonSearchOmniboxSuggestions` |
| 3 | Pref `performance_tuning.high_efficiency_mode.state = 2`, optionally `…aggressiveness = 2` (also in chrome://settings/performance) | pref | Background tabs are discarded and reload when the user returns to them | Raises the tab ceiling. Google reports "up to 40% and 10GB less memory" with Memory/Energy Saver ([Google blog](https://blog.google/products/chrome/new-chrome-features-to-save-battery-and-make-browsing-smoother/)). Not measured on one-renderer setups: freed Blink memory returns to the shared process, and its RSS may shrink less | Reload of discarded tabs loses form state. Playing media tabs are not discarded. Only time-based discards: `components/memory_pressure` has evaluators for Mac, Windows and Fuchsia only, so no pressure-driven discards on Linux | No |
| 4 | `--skia-resource-cache-limit-mb=40` `--skia-font-cache-limit-mb=8` `--decoded-image-working-set-budget-mb=96` `--enable-aggressive-release-policy` `--tile-manager-low-mem-policy-bytes-limit-reduction-factor=2` | neva switches | Smaller GPU/raster caches. Image-heavy pages decode again when scrolled back | Estimate: tens of MB in GPU and renderer. Values are LG's WAM TV values ([webapp-mgr.sh.in](https://github.com/webosose/wam/blob/master/files/launch/systemd/webapp-mgr.sh.in), lite profile uses 40/1 for skia). All five exist in M151 and are passed to the renderer (`render_process_host_impl.cc`). The decoded-image and release-policy ones apply under `USE_NEVA_APPRUNTIME`, which `out/tv` defines | More re-rasterisation, so scroll can get worse. Measure rAF on Wikipedia and YouTube home | Partly: `--mem-pressure-gpu-cache-size-reduction-factor=4` and `--force-gpu-mem-available-mb=128` are in run.sh |
| 5 | `--disable-features=BrowsingTopics,InterestGroupStorage,Fledge,SharedStorageAPI,FencedFrames,PrivateAggregationApi,ConversionMeasurement` (all on by default in M151) | features | Privacy Sandbox ad APIs (Topics, Protected Audience, Shared Storage, Attribution Reporting). The TV blocks ads anyway | Small. Estimate: these APIs need the privacy-sandbox attestation component, which never arrives with `--disable-component-update`, so most of them are already inert. The win is storage and per-navigation bookkeeping. Precedent: ungoogled `disable-privacy-sandbox`, Cromite `Disable-privacy-sandbox` | Sites that feature-detect these APIs fall back. Low | No |
| 6 | Packaging: ship only the `en-US` locale pak (plus the owner's UI language) | package.sh | Other UI languages. run.sh forces `--lang=en-US` | Flash only: `locales/` is 115.6 MB of the 233 MB install. No RAM or speed gain | None while `--lang` is fixed | No |
| 7 | GN batch that passes `gn gen` together: `enable_reporting=false`, `enable_paint_preview=false`, `enable_lens_desktop=false`, `use_on_device_model_service=false`, `enable_media_remoting=false`, `use_bluez=false`, `use_mpris=false`, `enable_platform_apps=false`, `enable_hosted_apps=false`, `enable_bound_session_credentials=false`, `enable_device_bound_sessions=false` | GN | Reporting API/NEL, paint previews, Google Lens, on-device Gemini, Cast remoting, Web Bluetooth (BlueZ over D-Bus), MPRIS media keys (already off at runtime), Chrome Apps, device-bound Google sessions | Small. Estimate: a few MB of binary and relocations. The whole batch removes 66 targets. ungoogled, Cromite and Bromite set `enable_reporting=false` | Compile not tested. Web Bluetooth disappears: the TV has no BlueZ for Chrome anyway | No |
| 8 | GN `enable_swiftshader=false`, `enable_vulkan=false`, `use_dawn=false` (gn gen passes) | GN | SwiftShader (software WebGL/Vulkan), Vulkan, Dawn/WebGPU. WebGPU already crashes on Mali and run.sh turns it off. Cobalt sets the same three ([cobalt linux_common.gn](https://github.com/youtube/cobalt/blob/main/cobalt/build/configs/linux_common.gn)) | 3.3 MB less install (`libvk_swiftshader.so`, `libvulkan.so.1`), smaller binary without Dawn | With `CN_GPU=off` (`--disable-gpu`) WebGL had SwiftShader as its fallback. Without it WebGL is gone on those TVs. The `webgpu=on` option in media.opts stops working | Runtime only: `Vulkan`, `WebGPUService` off in run.sh |
| 9 | `--disable-features=PartitionAllocSchedulerLoopQuarantine` (on by default in M151) | feature | A use-after-free mitigation: freed memory waits in quarantine until the task ends | Estimate: some CPU per free and some held memory | Security cost, on top of `--no-sandbox`. Leave on unless the A/B shows a clear gain. Do not touch `PartitionAllocMemoryReclaimer`: it returns memory | No (BackupRefPtr is already compiled out: `enable_backup_ref_ptr_support = false`) |
| 10 | GN `enable_gwp_asan = false` (gn gen passes) | GN | Sampling heap-corruption detector. Its reports go to crash upload, which this build does not do | Small memory and CPU. Estimate | A security mitigation, but its main value is the crash reports we do not collect | No |
| 11 | Pref `safebrowsing.enabled = false` | pref | Safe Browsing checks. Its list never updates here: `--disable-background-networking` stops V4 updates (`chrome_v4_protocol_config_provider.cc`) and there is no Google API key | Small: one check per navigation and resource against an empty database. Estimate | None beyond what is already lost | No (GN `safe_browsing_mode=0` fails gn gen, see below) |
| 12 | Prefs `browser.enable_spellchecking = false`, `plugins.always_open_pdf_externally = true`; `--disable-features=Journeys,PageContentAnnotations`; `--disable-domain-reliability` | prefs, features, switch | Spellcheck in text fields, the built-in PDF viewer (PDFs download instead), history "Journeys" clustering, page annotations, Google-domain reliability beacons | Small each. Estimate. ungoogled has a `disable-domain-reliability` patch | PDF viewer loss is user-visible. Keep it if PDFs matter | No |
| 13 | `--disable-features=AutofillServerCommunication` (on by default); pref `credentials_enable_service = false` | feature, pref | Crowdsourced form-type queries to Google on pages with forms. The password-save bubble. Typing forms with a remote is rare | Small. Estimate. Without a Google API key the queries fail anyway. ungoogled has `disable-autofill-download-manager` | Local autofill keeps working. Saved passwords stop being offered for saving | Partly: `--password-store=basic` keeps passwords out of a keyring |
| 14 | `--js-flags=--lite-mode` (or GN `v8_enable_lite_mode = true`, which webOS OSE offers as `v8_lite`) | V8 | TurboFan, feedback vectors and ICs | V8 heap about 22 % smaller, but page load 12 % slower and V8 CPU time +120 % without feedback vectors ([v8.dev/blog/v8-lite](https://v8.dev/blog/v8-lite)). `--jitless`: Speedometer 2 about 40 % slower ([v8.dev/blog/jitless](https://v8.dev/blog/jitless)) | Not a fit: speed comes first here | No. Rejected |

### No change

These cost nothing while unused, or the TV needs them:

| Item | Why it stays |
|---|---|
| WebRTC (`rtc_*`, `media_use_openh264`) | Issue #6: Meta Quest casting needs WebRTC with H.264 |
| WebUSB, WebSerial, WebHID, Web Bluetooth (runtime) | Behind a permission prompt. No idle cost. Bluetooth can go with the GN batch (#7) |
| Shopping (`ShoppingList`), Glic, Lens overlay | `ShoppingList` is off by default in M151. The defaults of `Glic` and `LensOverlay` depend on a platform buildflag (`IS_MAC`, `IS_ANDROID`), not checked further. The field trial config turns Glic on, see #1 |
| Side panel, reading list, tab groups, profile picker | UI with no background work. The profile picker shows only with several profiles |
| `MediaSession*` features | Patch 0049's screensaver guard counts media sessions |
| `HeavyAdIntervention`, `PartitionAllocMemoryReclaimer`, `IntensiveWakeUpThrottling` | On by default and they save resources. Keep them |
| UMA histograms | `UI_LATENCY.md` reads them. Metrics upload is off anyway: no consent in a Chromium build |
| `include_transport_security_state_preload_list` | HSTS preload, a security floor. Cobalt drops it, a general browser should not |

### Already off in our build

From `cr151/upstream/source/package/run.sh`, `source/args.gn`, `cr151/args.delta.gn` and `cr151/package.sh`:

- Runtime: Translate, OptimizationHints, OptimizationGuideModelDownloading, MediaRouter, BackForwardCache, Vulkan,
  ContextualTasks*, PreloadTopChromeWebUI, SpareRenderer, SpareRendererForSitePerProcess, IsolateOrigins,
  site-per-process, WebUIToolbar* and the WebUI omnibox popups, AudioServiceOutOfProcess, HardwareMediaKeyHandling,
  WebGPUService and WebGPUBlobCache; `--disable-sync`, `--disable-background-networking`,
  `--disable-component-update`, `--disable-component-extensions-with-background-pages`, `--disable-breakpad`,
  `--enable-low-end-device-mode`, `--renderer-process-limit=1`, `--process-per-site`, `--in-process-gpu`,
  NetworkServiceInProcess2, a 192 MB JS heap, MSE buffer caps, a 32 MB disk cache.
- Omnibox trim (package.sh): fewer providers, 5 rows, suggestion polling delay, MlUrlScoring, UrlScoringModel,
  MlUrlScoreCaching, AimEnabled, AllowAiModeMatches, OmniboxMiaZPS, PreconnectNonSearchOmniboxSuggestions.
- GN: `enable_nacl`, `enable_widevine`, `enable_vr`, `enable_openxr`, `enable_hangout_services_extension`,
  `enable_remoting`, `enable_print_preview`, `enable_libaom`, `use_cups`, `use_kerberos`, `use_gnome_keyring`,
  `enable_backup_ref_ptr_support` all false; `exclude_unwind_tables`, `symbol_level = 0`.

## Field trial testing config

- `components/variations/service/BUILD.gn`: `fieldtrial_testing_enabled = !disable_fieldtrial_testing_config` outside
  Chrome-branded Android. `out/tv/gen/components/variations/service/buildflags.h` has `FIELDTRIAL_TESTING_ENABLED() (1)`.
- `variations_field_trial_creator.cc`, `ShouldUseFieldTrialTestingConfig()`: in a non-Chrome-branded build the config
  is applied unless `--disable-field-trial-config` or `--variations-server-url` is on the command line.
  `--enable-features` / `--disable-features` do not stop it, they only override single features.
- `testing/variations/fieldtrial_testing_config.json` in our tree: 1 336 studies, 663 for Linux, 753 features enabled
  and 48 disabled by their first experiment (what the creator applies).
- Groups among the 753 that matter for a TV:
  - AI and Gemini: Glic and about 40 Glic* features, AnnotatedPageContentExtraction, ContentAnnotator,
    HistoryEmbeddings, OptimizationGuideOnDeviceModel, OnDeviceModelBackgroundDownload, AutofillModelPredictions.
  - Preloading: AutoSpeculationRules, DsePreload2, NewTabPageTriggerForPrefetch, BookmarkTriggerForPrefetch,
    SearchNavigationPrefetch, Prerender2WarmUpCompositor*, LCPPPrefetchSubresource, SpeculativeServiceWorkerWarmUp.
  - Hardening with a CPU cost: PartitionAllocEventuallyZeroFreedMemory, PartitionAllocUnretainedDanglingPtr,
    V8Flag_zero_unused_memory, V8Flag_verify_bytecode_light.
  - Memory-positive (re-enable if they help): Canvas2DHibernation*, ClearCanvasResourcesInBackground,
    KillSpareRenderOnMemoryPressure, WebGLDiscardBackBuffer, V8MemoryReducerDelay, MemoryCoordinatorLastResortGC.
- The release app 0.0.66 is built the same way, so this applies to their build as well.

## GN args that fail `gn gen` in M151

Do not retry these without a patch. Each fails on an `assert()` in a BUILD.gn that chrome still depends on, or on
unresolved dependencies:

| Arg | Error |
|---|---|
| `safe_browsing_mode = 0` | Unresolved dependencies (ungoogled and Bromite patch around it) |
| `enable_mdns = false`, `enable_service_discovery = false` | Assert in `chrome/browser/local_discovery/BUILD.gn` (printing needs it, see args.gn) |
| `enable_screen_ai_service = false` | Assert in `services/screen_ai/public/cpp/BUILD.gn` |
| `build_with_model_execution = false` | Assert in `chrome/browser/ai/BUILD.gn` |
| `enable_on_device_translation = false` | Assert in `components/on_device_translation/BUILD.gn` |
| `enable_compose = false` | Assert in `chrome/browser/compose/BUILD.gn` |
| `enable_supervised_users = false` | Assert in `chrome/test/BUILD.gn` |
| `enable_background_mode = false` | Assert in `chrome/browser/background/extensions/BUILD.gn` |
| `enable_captive_portal_detection = false` | Unresolved dependencies |
| `enable_speech_service = false` | Assert in `chrome/services/speech/BUILD.gn` |
| `enable_pdf = false`, `enable_printing = false` | Already recorded in `source/args.gn` |

`enable_glic` is not a GN arg in M151: Glic is a runtime feature only.

## WAM switches that do not exist in M151

`--max-unused-resource-memory-usage-percentage` and `--disable-low-res-tiling` from LG's WAM launch script are not in
this tree. `--enable-key-event-throttling` exists (`components/input/switches.cc`) but is about input, not memory.

## Sources

- Chromium 151.0.7922.108 tree (pinned in `cr151/upstream/COMMIT`), files named in the rows.
- ungoogled-chromium [flags.gn](https://github.com/ungoogled-software/ungoogled-chromium/blob/master/flags.gn),
  [patches/series](https://github.com/ungoogled-software/ungoogled-chromium/blob/master/patches/series) (Chromium 157).
- Cromite [cromite.gn_args](https://github.com/uazo/cromite/blob/master/build/cromite.gn_args),
  [patch list](https://github.com/uazo/cromite/blob/master/build/cromite_patches_list.txt) (Chromium 153).
- Bromite [bromite.gn_args](https://github.com/bromite/bromite/blob/master/build/bromite.gn_args) (archived, Chromium 108).
- Thorium [args.gn](https://github.com/Alex313031/thorium/blob/main/args.gn).
- webOS OSE [webruntime_120.bb](https://github.com/webosose/meta-webosose/blob/master/meta-webos/recipes-webos/chromium/webruntime_120.bb),
  [WAM launch script](https://github.com/webosose/wam/blob/master/files/launch/systemd/webapp-mgr.sh.in).
- Cobalt [common.gn](https://github.com/youtube/cobalt/blob/main/cobalt/build/configs/common.gn),
  [linux_common.gn](https://github.com/youtube/cobalt/blob/main/cobalt/build/configs/linux_common.gn).
- V8 [lite mode](https://v8.dev/blog/v8-lite), [jitless](https://v8.dev/blog/jitless).
- Chromium [site isolation overhead](https://www.chromium.org/Home/chromium-security/site-isolation/),
  [timer throttling](https://developer.chrome.com/blog/timer-throttling-in-chrome-88).
- WebOS-Chromium [issue #6](https://github.com/sarahahzub/WebOS-Chromium/issues/6) (WebGPU on Mali),
  [issue #12](https://github.com/sarahahzub/WebOS-Chromium/issues/12) (thread priority).
