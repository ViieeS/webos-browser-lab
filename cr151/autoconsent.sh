#!/bin/sh
# Builds a DuckDuckGo autoconsent add-on (cookie-banner auto-reject) from the npm package's prebuilt MV3 add-on,
# dist/addon-mv3: the package has no other extension build. package.sh ships the lean-frames variant; the bench
# (bench/consent_prep.sh) builds all four to compare them (FINDINGS.md, "Cookie banners").
#   test          DuckDuckGo's test extension with its debug logging and self-timing defaults off, the rest unchanged
#   lean          + rules and config kept in the service worker's memory: the test build reads its 516 KB rule set
#                 and its config from chrome.storage for every message of every frame, and logs the filtered rules
#                 as JSON. No toolbar icon updates (each one decodes a PNG). No popup mutation observer (the library's
#                 own default; the test build forces it on). Rules are not copied into storage at install, so the
#                 full rules.json (opt-in steps only) is dropped.
#   lean-noh      lean without heuristic detection (the generic "reject" button search)
#   lean-frames   lean with the content script only in main frames and in the subframes a rule can act in
#                 (autoconsent_frames.py): 13 % CPU on an ad-heavy page against 24 % for test, same rejects.
#                 Its CMP detection retries wait until the user has not scrolled or pressed a key for 1 s.
# usage: autoconsent.sh <autoconsent-X.Y.Z.tgz> <sha256> <variant> <out dir>     the add-on ends up in <out dir>
set -eu
TGZ=$1 SHA=$2 VARIANT=$3 OUT=$4
die() { echo "autoconsent.sh: $*" >&2; exit 1; }
case $VARIANT in test | lean | lean-noh | lean-frames) ;; *) die "unknown variant $VARIANT" ;; esac
if command -v sha256sum >/dev/null; then SUM="sha256sum"; else SUM="shasum -a 256"; fi
echo "$SHA  $TGZ" | $SUM -c --quiet - || die "sha256 mismatch: $TGZ"
X=$(mktemp -d)
trap 'rm -rf "$X"' EXIT
tar -xzf "$TGZ" -C "$X"
rm -rf "$OUT" && mkdir -p "$(dirname "$OUT")" && cp -R "$X/package/dist/addon-mv3" "$OUT"
cp "$X/package/LICENSE" "$OUT/LICENSE"   # MPL-2.0: the add-on carries its license text
BG=$OUT/background.bundle.js

perl -0pi -e 's/lifecycle: true,\n(\s+)rulesteps: true,\n(\s+)detectionsteps: false,\n(\s+)evals: true,\n(\s+)errors: true,\n(\s+)messages: false,\n(\s+)waits: true/lifecycle: false,\n$1rulesteps: false,\n$2detectionsteps: false,\n$3evals: false,\n$4errors: true,\n$5messages: false,\n$6waits: false/; s/storedConfig\.performanceLoggingEnabled = true;/storedConfig.performanceLoggingEnabled = false;/' "$BG"
grep -q 'storedConfig.performanceLoggingEnabled = false;' "$BG" && grep -q 'lifecycle: false,' "$BG" ||
	die "log defaults not changed"
[ "$VARIANT" = test ] && exit 0

perl -0pi -e '
s/const autoconsentConfig = await storageGet\("config"\) \|\| extensionDefaultConfig\(\);/const autoconsentConfig = await leanConfig();/;
s/filterCompactRules\(await storageGet\("rules"\),/filterCompactRules(await leanRules(),/;
s/\n\s*console\.log\("filtered rules:".*?\n/\n/;
s/\n\s*console\.log\("stored exceptions", storedExceptions\);\n/\n/;
s/(async function showOptOutStatus\(tabId, status, cmp = ""\) \{)/$1\n    return;/;
s/\n(\s+)loadRules\(\);\n(\s+)initConfig\(\);/\n$2initConfig();/;
s/storedConfig\.enablePopupMutationObserver = true;/storedConfig.enablePopupMutationObserver = false;/;
s/(\n\s*chrome\.runtime\.onInstalled\.addListener)/\n  let leanConfigP = null, leanRulesP = null;\n  chrome.storage.onChanged.addListener(() => { leanConfigP = null; });\n  function leanConfig() { return leanConfigP ||= storageGet("config").then((c) => c || extensionDefaultConfig()); }\n  function leanRules() { return leanRulesP ||= fetch(".\/compact-rules.json").then((r) => r.json()); }$1/;
' "$BG"
[ "$(grep -c -e 'await leanConfig()' -e 'await leanRules()' -e 'function leanConfig()' -e 'function leanRules()' \
	-e 'enablePopupMutationObserver = false;' "$BG")" = 5 ] || die "lean: a patch did not apply"
grep -q -e 'filtered rules:' -e 'stored exceptions' -e '    loadRules();' "$BG" && die "lean: a log or loadRules call is left"
grep -A1 'async function showOptOutStatus' "$BG" | grep -q '^    return;$' || die "lean: status icon not turned off"
rm "$OUT/rules.json"

case $VARIANT in
lean-noh)
	perl -0pi -e 's/storedConfig\.enableHeuristicDetection = true;/storedConfig.enableHeuristicDetection = false;/' "$BG"
	grep -q 'storedConfig.enableHeuristicDetection = false;' "$BG" || die "lean-noh: heuristics not turned off"
	;;
lean-frames)
	python3 "$(dirname "$0")/autoconsent_frames.py" "$OUT"
	# CMP detection retries (up to 20, each after 500 ms and a DOM mutation) rerun every rule's querySelectorAll, and a
	# scroll mutates the DOM: on Wikipedia rAF frames were 53 ms during a wheel scroll against 18 ms without the add-on.
	# Each retry now first waits for 1 s without wheel, scroll or keys (26 ms; same rejects on 7 sites, 2026-11-22).
	CS=$OUT/content.bundle.js
	perl -0pi -e '
s/\n(\s+)return this\.findCmp\(retries - 1\);/\n$1await cnWaitForUserIdle();\n$1return this.findCmp(retries - 1);/;
s/^("use strict";\n\(\(\) => \{\n)/$1  var cnLastInput = 0;\n  for (const t of ["wheel", "scroll", "keydown"]) addEventListener(t, () => { cnLastInput = performance.now(); }, { capture: true, passive: true });\n  async function cnWaitForUserIdle() { while (performance.now() - cnLastInput < 1e3) await new Promise((r) => setTimeout(r, 250)); }\n/;
' "$CS"
	[ "$(grep -c cnWaitForUserIdle "$CS")" = 2 ] || die "lean-frames: the idle wait did not apply"
	;;
esac
