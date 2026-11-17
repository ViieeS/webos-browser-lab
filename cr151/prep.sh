#!/bin/bash
# prep.sh: the parts of upstream setup-source.sh that do not download x64 toolchains, for an arm64 build host.
# Runs inside incontainer.sh (which already linked clang 23 and the Rust nightly into the tree). Safe to run again.
. /opt/cn/container/lib.sh
cd "$SRC"

# gn: the tree's buildtools/linux64/gn is x86_64. Build the DEPS revision natively.
GNREV=$(sed -n "s/.*'gn_version': 'git_revision:\([0-9a-f]*\)'.*/\1/p" DEPS)
if ! { file buildtools/linux64/gn | grep -q aarch64 && [ -f "$W/gn/.rev" ] && [ "$(cat "$W/gn/.rev")" = "$GNREV" ]; }; then
	log "gn $GNREV from source"
	[ -d "$W/gn/.git" ] || git clone -q https://gn.googlesource.com/gn "$W/gn"
	git -C "$W/gn" fetch -q origin "$GNREV" && git -C "$W/gn" checkout -q "$GNREV"
	(cd "$W/gn" && CC=clang-23 CXX=clang++-23 AR=llvm-ar-23 python3 build/gen.py --no-last-commit-position -q 2>/dev/null ||
		CC=clang-23 CXX=clang++-23 AR=llvm-ar-23 python3 build/gen.py --no-last-commit-position)
	printf '#ifndef OUT_LAST_COMMIT_POSITION_H_\n#define OUT_LAST_COMMIT_POSITION_H_\n#define LAST_COMMIT_POSITION_NUM 0\n#define LAST_COMMIT_POSITION "%s"\n#endif\n' \
		"${GNREV:0:12}" > "$W/gn/out/last_commit_position.h"
	ninja -C "$W/gn/out" gn > /dev/null
	cp -f "$W/gn/out/gn" buildtools/linux64/gn
	echo "$GNREV" > "$W/gn/.rev"
fi

# node: Chromium runs third_party/node/linux/node-linux-x64/bin/node; give it the image's arm64 node.
mkdir -p third_party/node/linux
ln -sfn /opt/node third_party/node/linux/node-linux-x64

# devtools-frontend ships x86_64 build tools: esbuild (its build script pins third_party/esbuild/esbuild) and
# rollup's native addon. Put the arm64 builds of the same versions in their place.
DT=third_party/devtools-frontend/src
file "$DT/third_party/esbuild/esbuild" | grep -q aarch64 || cp -f "$ESBUILD_BINARY_PATH" "$DT/third_party/esbuild/esbuild"
RV=$(sed -n 's/^  "version": "\(.*\)",/\1/p' "$DT/node_modules/rollup/package.json")
if [ ! -f "$DT/node_modules/@rollup/rollup-linux-arm64-gnu/package.json" ]; then
	log "rollup native addon $RV for linux-arm64"
	mkdir -p "$DT/node_modules/@rollup/rollup-linux-arm64-gnu"
	curl -fsSL "https://registry.npmjs.org/@rollup/rollup-linux-arm64-gnu/-/rollup-linux-arm64-gnu-$RV.tgz" |
		tar -xz -C "$DT/node_modules/@rollup/rollup-linux-arm64-gnu" --strip-components=1
fi

# Blink runs gperf from CIPD (x86_64). Its gperf.py ignores the exec failure and writes a header-only .cc, which
# compiles fine and fails only at the final link (FindProperty, FindValue, FindColor undefined). The image's gperf is
# the same 3.1.
file -L third_party/gperf/cipd/bin/gperf | grep -q aarch64 || ln -sfn /usr/bin/gperf third_party/gperf/cipd/bin/gperf

# Generated files that gclient hooks normally write (as upstream setup-source.sh).
python3 build/util/lastchange.py -o build/util/LASTCHANGE
python3 build/util/lastchange.py -m CHROMIUM --commit-position-header build/util/LASTCHANGE_commit_position.h || true
python3 build/util/lastchange.py -m GPU_LISTS_VERSION --revision-id-only --header gpu/config/gpu_lists_version.h
python3 build/util/lastchange.py -m SKIA_COMMIT_HASH -s third_party/skia --header skia/ext/skia_commit_hash.h
python3 build/util/lastchange.py -m DAWN_COMMIT_HASH -s third_party/dawn --revision gpu/webgpu/DAWN_VERSION \
	--header gpu/webgpu/dawn_commit_hash.h || true

# Rust target specs for the std build: the host is aarch64 here, not x86_64.
mkdir -p "$RUST_TARGET_PATH"
for t in aarch64-unknown-linux-gnu armv7-unknown-linux-gnueabi; do
	RUSTC_BOOTSTRAP=1 rustc -Z unstable-options --print target-spec-json --target "$t" > "$RUST_TARGET_PATH/$t.json"
done

# Host sysroot for host tools: the image's own arm64 userland, as in cr120.
ln -snf / build/linux/debian_bullseye_arm64-sysroot

log "clang: $(clang-23 --version | head -1) | gn: $(buildtools/linux64/gn --version) | rustc: $(rustc --version) | node: $(node --version)"
