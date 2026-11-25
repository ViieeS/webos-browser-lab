#!/bin/bash
# package.sh: our build -> IPK of a separate dev app (APP_ID below), with their launcher (built from their source with
# zig, as their BUILDING.md step 6), their run.sh and TV Tools, and their mkipk.py. NSS/NSPR: /work/nss/lib, taken
# from their 0.0.66 IPK (prebuilt MPL libraries, webOS 4 ships none; the C1 has its own but run.sh prefers these).
# Output: /work/dist/<APP_ID>_<VERSION>_arm.ipk, /work/dist/browser/ (unpacked, stripped), check-abi report.
. /opt/cn/container/lib.sh
need_sysroot   # check-abi compares against the sysroot's TV-SONAMES and glibc
# The default is the finished browser: the project Chromium TV, id com.viiees.chromiumtv, shown on the TV as plain
# "Chromium". CR151_APP_ID, CR151_APP_TITLE: a test variant next to it under another id. Not APP_ID: lib.sh has
# already set that from their config.env (org.nativechromium.browser).
APP_ID=${CR151_APP_ID:-com.viiees.chromiumtv}
APP_TITLE=${CR151_APP_TITLE:-"Chromium"}
VERSION=1.1.1
D=/work/dist; B=$D/browser; rm -rf "$D"; mkdir -p "$B"
cd "$OUT"
for f in chrome chrome_crashpad_handler *.pak icudtl.dat snapshot_blob.bin v8_context_snapshot.bin locales \
	libEGL.so libGLESv2.so libvk_swiftshader.so vk_swiftshader_icd.json libvulkan.so.1 \
	gen/components/resources/about_credits.html; do
	[ -e "$f" ] && cp -a "$f" "$B/"
done
find "$B" -type f | while read -r e; do
	head -c4 "$e" | grep -q ELF && "$LLVM/llvm-strip" --strip-unneeded "$e"
done
log "collected $(find "$B" -type f | wc -l) files, $(du -sh "$B" | cut -f1); chrome $(stat -c %s "$B/chrome") bytes stripped"
[ -d /work/nss/lib ] || die "no /work/nss/lib (NSS/NSPR from their IPK)"
set +e
LLVM=$LLVM SYSROOT=$SYSROOT TV_GLIBC_MAX=$TV_GLIBC_MAX TV_LOADER=$TV_LOADER python3 "$CN/container/check-abi.py" "$B" /work/nss/lib > "$D/abi-report.txt" 2>&1
abi=$?
set -e
tail -5 "$D/abi-report.txt"
[ $abi -eq 0 ] || die "check-abi found problems ($D/abi-report.txt)"

# launcher (their cnrun.c), zig as their build.sh expects
Z=/work/zig/zig
if [ ! -x "$Z" ]; then
	mkdir -p /work/zig
	curl -fsSL https://ziglang.org/download/0.13.0/zig-linux-aarch64-0.13.0.tar.xz | tar -xJ -C /work/zig --strip-components=1
fi
# Our launcher change, sent upstream: only a crash signal counts against the GPU, and two in a row turn it off.
patch -d "$CN" -p2 --forward -s < /cr151/launcher/gpu-state-crash-only.patch || die "launcher patch did not apply"
grep -q 'second crash' "$CN/package/launcher/cnrun.c" || die "launcher: gpu.state patch missing"
(cd "$CN/package/launcher" && ZIG=$Z OUT=$D/cnrun sh build.sh) 2>&1 | tail -2

# Our fontconfig setup (fonts.conf explains why): shipped as browser/fonts.conf, run.sh points FONTCONFIG_FILE at it.
cp /cr151/fonts.conf "$B/fonts.conf"
grep -q FONTCONFIG_FILE "$CN/package/run.sh" ||
	sed -i 's|^export LANG=|export FONTCONFIG_FILE=$D/browser/fonts.conf\nexport LANG=|' "$CN/package/run.sh"
grep -q '^export FONTCONFIG_FILE=' "$CN/package/run.sh" || die "run.sh: FONTCONFIG_FILE line not added"

# Omnibox trimmed for a TV (UI_LATENCY.md: key to screen 160 -> 94 ms). Upstream has it as an opt-in, media.opts
# "omnibox=lite"; Chromium TV turns it on by default, and "omnibox=full" in media.opts gives Chrome's own omnibox back.
sed -i "s|if grep -q 'omnibox=lite' \"\$T/media.opts\" 2>/dev/null; then|if ! grep -q 'omnibox=full' \"\$T/media.opts\" 2>/dev/null; then|" "$CN/package/run.sh"
grep -q "if ! grep -q 'omnibox=full' \"\$T/media.opts\" 2>/dev/null; then" "$CN/package/run.sh" ||
	die "run.sh: omnibox trim not turned on by default"

# Without this switch a non-Chrome-branded build applies Google's whole field trial testing config at every start:
# 659 trials, 738 features nobody chose for a TV. Off: browser process 25–35 MB smaller, same speed
# (TRIM_CANDIDATES.md, "Results"). The omnibox trial above stays: --force-fieldtrials is separate.
grep -q -- '--disable-field-trial-config' "$CN/package/run.sh" ||
	sed -i 's|^\t\t--enable-features=NetworkServiceInProcess2|\t\t--disable-field-trial-config \\\n&|' "$CN/package/run.sh"
[ "$(grep -c -- '^		--disable-field-trial-config \\$' "$CN/package/run.sh")" = 1 ] || die "run.sh: --disable-field-trial-config not added"
# The one study of that config that made JS faster: V8SqrtAllocationLimits, whose params are V8's own defaults. With
# it Speedometer is 0.737 against 0.722 with the config on and 0.711 without (TRIM_CANDIDATES.md, "Results").
grep -q -- '--sqrt-allocation-limits' "$CN/package/run.sh" ||
	sed -i 's|--js-flags="--max-old-space-size=192 --optimize-for-size$JS_LITE"|--js-flags="--max-old-space-size=192 --optimize-for-size --sqrt-allocation-limits$JS_LITE"|' "$CN/package/run.sh"
grep -q -- '--optimize-for-size --sqrt-allocation-limits\$JS_LITE"' "$CN/package/run.sh" || die "run.sh: --sqrt-allocation-limits not added"
# Wheel notches land without the scroll animation: notch latency 196 -> 142 ms on Wikipedia, 730 -> 556 ms on
# YouTube (INPUT_LATENCY.md). The owner tried it with the Magic Remote wheel and kept it.
grep -q -- '--disable-smooth-scrolling' "$CN/package/run.sh" ||
	sed -i 's|^\t\t--enable-features=NetworkServiceInProcess2|\t\t--disable-smooth-scrolling \\\n&|' "$CN/package/run.sh"
[ "$(grep -c -- '^		--disable-smooth-scrolling \\$' "$CN/package/run.sh")" = 1 ] || die "run.sh: --disable-smooth-scrolling not added"

# uBlock Origin Lite (ADBLOCK.md: complete mode blocks as well as full uBO here, MV3, no patch). The official release
# zip comes from /adblock (a .adblock/ folder next to the repository, mounted read-only; ADBLOCK.md says where to
# download it), checked against its sha256. It is unpacked and patched here, then packed into a CRX below.
UBOL_ZIP=/adblock/ubol/uBOLite_2026.1116.1650.chromium.zip
UBOL_SHA=67e084b34470c51c08fa9314b118b8cb73df3a72e90c6a3b536d041c92e61bbc
[ -f "$UBOL_ZIP" ] || die "no $UBOL_ZIP: add -v \"\$PWD/../.adblock:/adblock:ro\" to docker run"
echo "$UBOL_SHA  $UBOL_ZIP" | sha256sum -c --quiet - || die "uBO Lite zip: sha256 mismatch"
rm -rf "$B/ext/ubol" && mkdir -p "$B/ext/ubol"
python3 -c 'import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$UBOL_ZIP" "$B/ext/ubol"
# Complete mode on a fresh profile. The managed-storage policy ("defaultFiltering") would need a policy file under
# /etc, which is read-only on the TV, so the shipped default changes instead. A mode the user picks still wins.
sed -i "s|optimal: \[ 'all-urls' \],|optimal: [],|; s|complete: \[\],|complete: [ 'all-urls' ],|" "$B/ext/ubol/js/mode-manager.js"
grep -q "complete: \[ 'all-urls' \]," "$B/ext/ubol/js/mode-manager.js" && ! grep -q "optimal: \[ 'all-urls' \]," "$B/ext/ubol/js/mode-manager.js" ||
	die "uBO Lite: default mode not set to complete"
# uBO Lite is installed packed, from browser/extensions/ (Chrome's external extensions folder next to its binary):
# loaded with --load-extension it delayed the browser window by about 5 s, because Chrome parses and indexes all 56
# of its declarativeNetRequest rulesets (13 MB of JSON, 6 enabled) on the UI thread at every start. Packed, they are
# indexed once at install (FINDINGS.md, "uBO Lite delays the browser window"). The key fixes the extension id, so a
# new uBO Lite version updates the same extension and keeps its settings. A new key would install a second one.
UBOL_KEY=/adblock/ubol/crx-key.pem
[ -f "$UBOL_KEY" ] || die "no $UBOL_KEY: create it once with: openssl genrsa -out .adblock/ubol/crx-key.pem 2048"
UV=$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$B/ext/ubol/manifest.json")
mkdir -p "$B/extensions"
UBOL_ID=$(python3 /cr151/crx3.py "$B/ext/ubol" "$UBOL_KEY" "$B/extensions/ubol.crx") || die "uBO Lite: crx3.py failed"
printf '{"external_crx": "ubol.crx", "external_version": "%s"}\n' "$UV" > "$B/extensions/$UBOL_ID.json"
rm -rf "$B/ext/ubol"
log "uBO Lite $UV packed as $UBOL_ID"
# Earlier builds copied the unpacked uBO Lite into the data folder; the copy is no longer used.
python3 - "$CN/package/run.sh" <<'PY'
import sys
path = sys.argv[1]
s = open(path).read()
anchor = "\t# GPU check: the launcher sets CN_GPU=off"
assert s.count(anchor) == 1, "run.sh anchor changed"
s = s.replace(anchor, '\trm -rf "$S/ext/ubol" "$S/ext/.ubol"\n' + anchor)
open(path, "w").write(s)
PY
grep -q '^	rm -rf "\$S/ext/ubol" "\$S/ext/.ubol"$' "$CN/package/run.sh" || die "run.sh: old uBO Lite copy not removed"

# Cookie banners are rejected by DuckDuckGo autoconsent (MPL-2.0), the lean-frames build from autoconsent.sh
# (FINDINGS.md, "Cookie banners"). It rejected 7 of 11 banners and accepted none. uBO Lite's own Cookie Notices list
# stays off: it accepted everything on two sites. The npm package comes from /adblock like uBO Lite, checked against
# its sha256. The add-on loads from the read-only app folder: it has no declarativeNetRequest rules, so Chrome writes
# nothing into its folder.
AC_TGZ=/adblock/autoconsent/autoconsent-18.9.0.tgz
AC_SHA=04a49d0c180f1fcd8837e10dd45643d9af809608911c5791c7d15323ea89edcb
[ -f "$AC_TGZ" ] || die "no $AC_TGZ: add -v \"\$PWD/../.adblock:/adblock:ro\" to docker run"
sh /cr151/autoconsent.sh "$AC_TGZ" "$AC_SHA" lean-frames "$B/ext/autoconsent"
sed -i 's|--load-extension="$EXT" |--load-extension="$EXT,$B/ext/autoconsent" |' "$CN/package/run.sh"
grep -q -- '--load-extension="\$EXT,\$B/ext/autoconsent" ' "$CN/package/run.sh" ||
	die "run.sh: autoconsent not added to --load-extension"

# Tab limit 8 by default (TV Tools' own setting, 0 = no limit upstream). Heavy tabs ran out of memory at 15–19
# (ADBLOCK.md, "Many tabs"), and from the 8th on MemAvailable fell under 300 MB with zram nearly full. A limit the
# user saved in TV Tools still wins: tvLoad() lays saved settings over these defaults.
TVT_SETTINGS=$CN/package/ext/tvtools/settings.js
sed -i 's/^  tabLimit: 0, /  tabLimit: 8, /' "$TVT_SETTINGS"
grep -q '^  tabLimit: 8, ' "$TVT_SETTINGS" || die "TV Tools: default tab limit not set"

# "Auto" resolution with the full hardware decoder (NDL) is 4K, not upstream's 1080p: on the C1, YouTube 4K60 played
# at 1.00x, 60 fps, 0 dropped, and the owner saw it smooth on screen after a short unevenness at the start
# (FINDINGS.md, "Chromium TV: fonts, web apps, YouTube 4K60"). Auto rather than a 2160 default: software decoding
# and H.264-only decoders keep their lower caps, and a profile that saved "auto" gets 4K too.
sed -i 's/maxHeight: s.maxRes === "auto" ? (hw ? 1080 : 720)/maxHeight: s.maxRes === "auto" ? (hw \&\& !h264hw ? 2160 : hw ? 1080 : 720)/; s/any codec up to 1080p60 (bigger streams don.t fit the TV.s/any codec up to 2160p60 (Chromium TV, measured on the C1; upstream: 1080p, for the TV'"'"'s/' "$TVT_SETTINGS"
sed -i 's/if (id === "maxRes") return hw ? "Auto = 1080p" : "Auto = 720p";/if (id === "maxRes") return hw \&\& !h264hw ? "Auto = 4K" : hw ? "Auto = 1080p" : "Auto = 720p";/; s/if it does, go back to Auto or 1080p\./if it does, choose 1080p./' "$CN/package/ext/tvtools/ui.js"
grep -q 'hw && !h264hw ? 2160 : hw ? 1080 : 720' "$TVT_SETTINGS" && grep -q '"Auto = 4K"' "$CN/package/ext/tvtools/ui.js" &&
	grep -q 'if it does, choose 1080p\.' "$CN/package/ext/tvtools/ui.js" ||
	die "TV Tools: Auto resolution not raised to 4K"
# page.js uses its own copy of the defaults until the extension's settings reach a site for the first time.
sed -i 's/enabled: true, hardware: true, maxHeight: 1080, maxFps: 60,/enabled: true, hardware: true, maxHeight: 2160, maxFps: 60,/' "$CN/package/ext/tvtools/page.js"
grep -q 'hardware: true, maxHeight: 2160, maxFps: 60,' "$CN/package/ext/tvtools/page.js" ||
	die "TV Tools: Auto resolution not raised to 4K"

# Spotify gets the desktop user agent: with the TV one open.spotify.com serves a mobile "Open App" page with no web
# player (FINDINGS.md, "Which sites serve a TV version"). tvLoad() lays saved settings over the defaults, and a saved
# desktopSites list would hide a new default, so a profile without the marker gets spotify.com added on every load.
# The marker is saved with the next settings change, and from then on the user's list (spotify.com in it) wins.
sed -i 's/^  desktopSites: \[\],     /  desktopSites: ["spotify.com"], /' "$TVT_SETTINGS"
python3 - "$TVT_SETTINGS" <<'PY' || die "TV Tools: spotify.com not added to the saved desktop sites"
import sys
path = sys.argv[1]
s = open(path).read()
anchor = "    s.lite = tvLiteSetting(s.lite);\n"
assert s.count(anchor) == 1, "tvLoad anchor changed"
s = s.replace(anchor, anchor + (
    "    if (!s.ctvDesktopSpotify) {\n"
    "      if (!tvHostIn(\"open.spotify.com\", s.desktopSites)) s.desktopSites = s.desktopSites.concat([\"spotify.com\"]);\n"
    "      s.ctvDesktopSpotify = true;\n"
    "    }\n"))
open(path, "w").write(s)
PY
grep -q '^  desktopSites: \["spotify.com"\], ' "$TVT_SETTINGS" && grep -q 's.ctvDesktopSpotify = true;' "$TVT_SETTINGS" ||
	die "TV Tools: spotify.com not in the default desktop sites"

# Dark theme, on by default so white pages do not wear the OLED panel. TV Tools' "Dark theme" setting: On (dark
# browser UI, prefers-color-scheme: dark, and WebContentsForceDark darkens pages that have no dark design of their
# own), "Only sites' own" (no forced darkening, for pages it spoils) or Off. Both are start-up switches, so run.sh
# reads the setting from TV Tools' LevelDB like Lite mode, and a change applies the next time the browser opens.
# The feature goes into the existing --enable-features list: a second --enable-features switch would replace it.
python3 - "$TVT_SETTINGS" "$CN/package/ext/tvtools/ui.js" "$CN/package/run.sh" <<'PY' || die "dark theme not added"
import sys
def edit(path, anchor, new):
    s = open(path).read()
    assert s.count(anchor) == 1, f"{path}: anchor changed: {anchor!r}"
    open(path, "w").write(s.replace(anchor, new))
settings, ui, run = sys.argv[1:4]
edit(settings, "  pauseHidden: false ",
     '  darkTheme: "on",     // "on" | "sites" | "off": read by run.sh when the browser starts\n  pauseHidden: false ')
edit(ui, '  {\n    id: "uaMode",', (
    '  {\n'
    '    id: "darkTheme", title: "Dark theme", section: "browsing",\n'
    '    help: "Keeps bright white off the OLED screen. On: dark browser, and pages without a dark design are " +\n'
    '      "darkened too. Only sites\' own: pages turn dark only when the site has a dark design. " +\n'
    '      "Changes the next time the browser opens.",\n'
    '    options: [["on", "On"], ["sites", "Only sites\' own"], ["off", "Off"]]\n'
    '  },\n'
    '  {\n    id: "uaMode",'))
edit(run, "\tJS_LITE=\n", (
    "\t# Dark theme (TV Tools' \"Dark theme\", default On), read the same way as Lite mode. Added by package.sh.\n"
    "\tDARK_SET=on\n"
    "\tfor f in $(cd \"$LX\" 2>/dev/null && ls -t -- *.log *.ldb 2>/dev/null); do\n"
    "\t\tv=$(grep -a -o -E '\"darkTheme\":\"(on|sites|off)\"' \"$LX/$f\" 2>/dev/null | tail -1)\n"
    "\t\t[ -n \"$v\" ] || continue\n"
    "\t\tcase \"$v\" in *'\"sites\"') DARK_SET=sites ;; *'\"off\"') DARK_SET=off ;; esac\n"
    "\t\tbreak\n"
    "\tdone\n"
    "\tDARK_UI=; DARK_PAGES=\n"
    "\tcase \"$DARK_SET\" in on) DARK_UI=--force-dark-mode DARK_PAGES=,WebContentsForceDark ;; sites) DARK_UI=--force-dark-mode ;; esac\n"
    "\tJS_LITE=\n"))
edit(settings, "  pauseHidden: false ",
     '  gpu: "auto",         // "auto" | "on" | "off": read by run.sh when the browser starts\n  pauseHidden: false ')
edit(ui, '  {\n    id: "uaMode",', (
    '  {\n'
    '    id: "gpu", title: "GPU", section: "browsing",\n'
    '    help: "Auto: the browser draws with the GPU unless it crashed twice in a row with it. On: always, and " +\n'
    '      "Auto tries the GPU again afterwards. Off: draws in software, slower. Changes the next time the browser opens.",\n'
    '    options: [["auto", "Auto"], ["on", "On"], ["off", "Off"]]\n'
    '  },\n'
    '  {\n    id: "uaMode",'))
edit(run, "\tJS_LITE=\n", (
    "\t# GPU (TV Tools' \"GPU\", default Auto = the launcher's check). On also deletes the launcher's crash record, so\n"
    "\t# Auto tries the GPU again later. media.opts gpu=on / gpu=off still win (tests). Added by package.sh.\n"
    "\tGPU_SET=auto\n"
    "\tfor f in $(cd \"$LX\" 2>/dev/null && ls -t -- *.log *.ldb 2>/dev/null); do\n"
    "\t\tv=$(grep -a -o -E '\"gpu\":\"(auto|on|off)\"' \"$LX/$f\" 2>/dev/null | tail -1)\n"
    "\t\t[ -n \"$v\" ] || continue\n"
    "\t\tcase \"$v\" in *'\"on\"') GPU_SET=on ;; *'\"off\"') GPU_SET=off ;; esac\n"
    "\t\tbreak\n"
    "\tdone\n"
    "\t# whole words only: media.opts \"webgpu=on\" is not \"gpu=on\"\n"
    "\tif ! grep -q -E '(^|[[:space:]])gpu=(on|off)([[:space:]]|$)' \"$T/media.opts\" 2>/dev/null; then\n"
    "\t\tcase \"$GPU_SET\" in on) GPU_OFF=; rm -f \"$D/data/gpu.state\" \"$T/gpu.state\" ;; off) GPU_OFF=--disable-gpu ;; esac\n"
    "\t\t# a mode the user chose: the launcher's crash count must not judge this run (gpu.forced)\n"
    "\t\t[ \"$GPU_SET\" != auto ] && : > \"$T/gpu.forced\"\n"
    "\t\t# the launcher logged its own verdict before this ran\n"
    "\t\t[ \"$GPU_SET\" = on ] && [ \"$CN_GPU\" = off ] && echo \"run.sh gpu: on (TV Tools GPU = On, overrides the launcher)\" >> \"$T/media.log\"\n"
    "\t\t[ \"$GPU_SET\" = off ] && [ \"$CN_GPU\" != off ] && echo \"run.sh gpu: off (TV Tools GPU = Off)\" >> \"$T/media.log\"\n"
    "\tfi\n"
    "\tJS_LITE=\n"))
edit(run, "--enable-features=NetworkServiceInProcess2$OMNI_ON ",
     "--enable-features=NetworkServiceInProcess2$DARK_PAGES$OMNI_ON ")
edit(run, "--enable-spatial-navigation ", "--enable-spatial-navigation $DARK_UI ")
PY

tar --format=posix -C "$D" -cf - browser | zstd -T0 -10 -q -o "$D/browser.tar.zst"
sed -i "s/^APP_ID=.*/APP_ID=$APP_ID/; s/^APP_TITLE=.*/APP_TITLE=$APP_TITLE/" "$CN/config.env"
python3 "$CN/package/mkipk.py" --browser "$D/browser.tar.zst" --version "$VERSION" --launcher "$D/cnrun" \
	--requires "glibc=2.24,webos=webOS 4.4" --lib-dir /work/nss/lib --out "$D" 2>&1 | tail -3
ls -l "$D"/*.ipk
