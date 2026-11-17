#!/bin/bash
# Runs one build step inside the cr151 image, with the paths upstream's container scripts expect:
#   /opt/cn = upstream/source + our patches (patches/) + args.gn with args.delta.gn and args.host.gn appended,
#   /work = volume cr151work (tree from fetch.sh, sysroot, builtins, out/), /vol = volume cr151vol (their snapshots).
# usage (from browser/): docker run --rm -v cr151work:/work -v cr151vol:/vol -v "$PWD/cr151:/cr151:ro" cr151 \
#          bash /cr151/incontainer.sh <step> [args]
# steps, in order: sysroot, sysroot-compat, prep, builtins, patch, gen, build [targets], collect
set -euo pipefail
rm -rf /opt/cn && cp -r /cr151/upstream/source /opt/cn
cp /cr151/patches/*.patch /opt/cn/patches/
cat /cr151/args.delta.gn /cr151/args.host.gn >> /opt/cn/args.gn
# arm64 build host: the compat sysroot step runs wayland-scanner 1.18 from an amd64 .deb; take the arm64 one.
sed -i 's|http://archive.ubuntu.com/ubuntu/pool/main/w/wayland/libwayland-bin_1.18.0-1ubuntu0.1_amd64.deb|http://ports.ubuntu.com/ubuntu-ports/pool/main/w/wayland/libwayland-bin_1.18.0-1ubuntu0.1_arm64.deb|' \
	/opt/cn/container/build-sysroot-compat.sh
# The tree lives in volume cr151work (fetch.sh), not in a Modal "src" snapshot.
sed -i 's|^need_src() {.*|need_src() { [ -d "$SRC/.." ] \&\& [ -f "$SRC/DEPS" ] \|\| die "no tree at $SRC: run fetch.sh first"; }|' \
	/opt/cn/container/lib.sh
# Builtins must match OUR compiler (clang 23 from apt.llvm.org, release/23.x), not Chromium's pinned llvmorg-23-init.
sed -i 's|^FULL=\$(curl.*|FULL=release/23.x|' /opt/cn/container/build-builtins.sh

# clang 23 at Chromium's default clang_base_path. Rust comes through args.host.gn (rust_sysroot_absolute).
if [ -d /work/c151/src ]; then
	mkdir -p /work/c151/src/third_party/llvm-build
	ln -sfn /usr/lib/llvm-23 "/work/c151/src/third_party/llvm-build/Release+Asserts"
	# some std rules name //third_party/rust-toolchain/bin/rustc directly, even with rust_sysroot_absolute
	ln -sfn /opt/rust-sysroot /work/c151/src/third_party/rust-toolchain
fi

case "$1" in
	sysroot) exec bash /opt/cn/container/build-sysroot.sh ;;
	sysroot-compat) exec bash /opt/cn/container/build-sysroot-compat.sh ;;
	builtins) exec bash /opt/cn/container/build-builtins.sh ;;
	prep) exec bash /cr151/prep.sh ;;
	patch) exec bash /cr151/patch.sh ;;
	gen) exec bash /cr151/build.sh gen ;;
	build) shift; exec bash /cr151/build.sh build "$@" ;;
	package) exec bash /cr151/package.sh ;;
	*) exec bash "$1" ;;
esac
