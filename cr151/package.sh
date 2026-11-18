#!/bin/bash
# package.sh: our build -> IPK of a separate dev app (APP_ID below), with their launcher (built from their source with
# zig, as their BUILDING.md step 6), their run.sh and TV Tools, and their mkipk.py. NSS/NSPR: /work/nss/lib, taken
# from their 0.0.66 IPK (prebuilt MPL libraries, webOS 4 ships none; the C1 has its own but run.sh prefers these).
# Output: /work/dist/<APP_ID>_<VERSION>_arm.ipk, /work/dist/browser/ (unpacked, stripped), check-abi report.
. /opt/cn/container/lib.sh
need_sysroot   # check-abi compares against the sysroot's TV-SONAMES and glibc
# CR151_APP_ID, CR151_APP_TITLE: a variant next to it (com.viiees.cr151p: + patch 0103). Not APP_ID: lib.sh has
# already set that from their config.env (org.nativechromium.browser).
APP_ID=${CR151_APP_ID:-com.viiees.cr151}
APP_TITLE=${CR151_APP_TITLE:-"Chromium 151 (own build)"}
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

tar --format=posix -C "$D" -cf - browser | zstd -T0 -10 -q -o "$D/browser.tar.zst"
sed -i "s/^APP_ID=.*/APP_ID=$APP_ID/; s/^APP_TITLE=.*/APP_TITLE=$APP_TITLE/" "$CN/config.env"
python3 "$CN/package/mkipk.py" --browser "$D/browser.tar.zst" --version "$VERSION" --launcher "$D/cnrun" \
	--requires "glibc=2.24,webos=webOS 4.4" --lib-dir /work/nss/lib --out "$D" 2>&1 | tail -3
ls -l "$D"/*.ipk
