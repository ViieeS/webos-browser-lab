#!/bin/bash
# package.sh: our build -> IPK of a separate dev app (APP_ID below), with their launcher (built from their source with
# zig, as their BUILDING.md step 6), their run.sh and TV Tools, and their mkipk.py. NSS/NSPR: /work/nss/lib, taken
# from their 0.0.66 IPK (prebuilt MPL libraries, webOS 4 ships none; the C1 has its own but run.sh prefers these).
# Output: /work/dist/<APP_ID>_<VERSION>_arm.ipk, /work/dist/browser/ (unpacked, stripped), check-abi report.
. /opt/cn/container/lib.sh
need_sysroot   # check-abi compares against the sysroot's TV-SONAMES and glibc
# The default is the finished browser, Chromium TV. CR151_APP_ID, CR151_APP_TITLE: a test variant next to it under
# another id. Not APP_ID: lib.sh has already set that from their config.env (org.nativechromium.browser).
APP_ID=${CR151_APP_ID:-com.viiees.chromiumtv}
APP_TITLE=${CR151_APP_TITLE:-"Chromium TV"}
VERSION=0.0.66
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
(cd "$CN/package/launcher" && ZIG=$Z OUT=$D/cnrun sh build.sh) 2>&1 | tail -2

# Our fontconfig setup (fonts.conf explains why): shipped as browser/fonts.conf, run.sh points FONTCONFIG_FILE at it.
cp /cr151/fonts.conf "$B/fonts.conf"
grep -q FONTCONFIG_FILE "$CN/package/run.sh" ||
	sed -i 's|^export LANG=|export FONTCONFIG_FILE=$D/browser/fonts.conf\nexport LANG=|' "$CN/package/run.sh"
grep -q '^export FONTCONFIG_FILE=' "$CN/package/run.sh" || die "run.sh: FONTCONFIG_FILE line not added"

# Omnibox trimmed for a TV (UI_LATENCY.md: key to screen 160 -> 94 ms): fewer providers, 5 rows, suggest after a
# pause. The mask keeps HistoryFuzzyProvider (1 << 16): typo matching over history measured at no cost.
# Appended to run.sh's own feature lists so its WebGPU toggle keeps working.
OMNI_OFF=OmniboxDynamicMaxAutocomplete,OmniboxRichAutocompletion,MlUrlScoring,UrlScoringModel,MlUrlScoreCaching,AimEnabled,AllowAiModeMatches,OmniboxMiaZPS,PreconnectNonSearchOmniboxSuggestions
OMNI_ON="OmniboxUIExperimentMaxAutocompleteMatches:UIMaxAutocompleteMatches/5 --force-fieldtrials=OmniboxBundledExperimentV1/TV/ --force-fieldtrial-params=OmniboxBundledExperimentV1.TV:DisableProviders/201221632/SuggestPollingDelayMs/400/MeasureSuggestPollingDelayFromLastKeystroke/true"
grep -q OmniboxBundledExperimentV1 "$CN/package/run.sh" ||
	sed -i "s|HardwareMediaKeyHandling\\\$WEBGPU_OFF|HardwareMediaKeyHandling,$OMNI_OFF\$WEBGPU_OFF|; s|--enable-features=NetworkServiceInProcess2 |--enable-features=NetworkServiceInProcess2,$OMNI_ON |" "$CN/package/run.sh"
[ "$(grep -c -e "$OMNI_OFF\\\$WEBGPU_OFF" -e 'DisableProviders/201221632' "$CN/package/run.sh")" = 2 ] ||
	die "run.sh: omnibox trim not added"

# uBlock Origin Lite (ADBLOCK.md: complete mode blocks as well as full uBO here, MV3, no patch). The official release
# zip comes from /adblock (a .adblock/ folder next to the repository, mounted read-only; ADBLOCK.md says where to
# download it), checked against its sha256. It ships as
# browser/ext/ubol and loads next to TV Tools: Chrome keeps only the last --load-extension, so one comma list.
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
# uBO Lite runs from a copy in the data folder, as TV Tools does: Chrome writes the indexed declarativeNetRequest
# rulesets into an unpacked extension's own _metadata/, and the installed app folder is read-only (from there Chrome
# drops the extension without a word). The copy is refreshed when the shipped uBO Lite version changes.
python3 - "$CN/package/run.sh" <<'PY'
import sys
path = sys.argv[1]
s = open(path).read()
if "ext/ubol" not in s:
    anchor = "\t# GPU check: the launcher sets CN_GPU=off"
    copy = ('\tUBOL=$S/ext/ubol\n'
            '\tUV=$(sed -n \'s/.*"version": *"\\([^"]*\\)".*/\\1/p\' "$B/ext/ubol/manifest.json")\n'
            '\tif [ "$(cat "$S/ext/.ubol" 2>/dev/null)" != "$UV" ] || [ ! -f "$UBOL/manifest.json" ]; then\n'
            '\t\trm -rf "$UBOL" && mkdir -p "$S/ext" && cp -r "$B/ext/ubol" "$UBOL" && echo "$UV" > "$S/ext/.ubol" ||\n'
            '\t\t\tUBOL=$B/ext/ubol\n'
            '\tfi\n')
    assert s.count(anchor) == 1 and s.count('--load-extension="$EXT" ') == 1, "run.sh anchors changed"
    s = s.replace(anchor, copy + anchor).replace('--load-extension="$EXT" ', '--load-extension="$EXT,$UBOL" ')
    open(path, "w").write(s)
PY
grep -q -- '--load-extension="\$EXT,\$UBOL"' "$CN/package/run.sh" && grep -q '^	UBOL=\$S/ext/ubol$' "$CN/package/run.sh" ||
	die "run.sh: uBO Lite not added to --load-extension"

tar --format=posix -C "$D" -cf - browser | zstd -T0 -10 -q -o "$D/browser.tar.zst"
sed -i "s/^APP_ID=.*/APP_ID=$APP_ID/; s/^APP_TITLE=.*/APP_TITLE=$APP_TITLE/" "$CN/config.env"
python3 "$CN/package/mkipk.py" --browser "$D/browser.tar.zst" --version "$VERSION" --launcher "$D/cnrun" \
	--requires "glibc=2.24,webos=webOS 4.4" --lib-dir /work/nss/lib --out "$D" 2>&1 | tail -3
ls -l "$D"/*.ipk
