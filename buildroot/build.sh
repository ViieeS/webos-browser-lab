#!/bin/sh
# Builds WPE WebKit for the C1 (webOS 6, armv7 softfp) with buildroot-nc4 inside Docker.
# The tree lives in the "wpe-br" volume: buildroot needs a case-sensitive filesystem, and the
# Mac mount is case-insensitive and slow.
# usage: browser/buildroot/build.sh [make target...]
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
MCPU_LINE=
if [ -n "${WEBKIT_MCPU:-}" ]; then
  F="-D_LARGEFILE_SOURCE -D_LARGEFILE64_SOURCE -D_FILE_OFFSET_BITS=64 -mcpu=$WEBKIT_MCPU"
  MCPU_LINE="WPEWEBKIT_CONF_OPTS += -DCMAKE_C_FLAGS='$F' -DCMAKE_CXX_FLAGS='$F' # webos-softfp"
fi
BR_REF=322ff04e625a7927338c2ac5f3d02cd0511c9b90   # openlgtv/buildroot-nc4, the commit tv-wpe-build proved

docker build -q -t wpe-br "$HERE" >/dev/null
docker run --rm -e MCPU_LINE="$MCPU_LINE" -v wpe-br:/work -v "$HERE":/src:ro wpe-br sh -euc "
  if [ ! -d /work/buildroot ]; then
    git clone -q --filter=blob:none https://github.com/openlgtv/buildroot-nc4.git /work/buildroot
    git -C /work/buildroot checkout -q $BR_REF
  fi
  cd /work/buildroot
  # JavaScriptCore's ARMv7 JIT requires a hard-float userspace; webOS is softfp. Patch 0006 makes
  # JIT operations use the VFP calling convention and opens the gate. WebAssembly stays off: its
  # tiers carry their own VFP assumptions. -O2 was slower than buildroot's -Os on the C1, so no flag
  # overrides. The line is rewritten on every run so option changes take effect.
  sed -i '/webos-softfp/d' package/wpewebkit/wpewebkit.mk
  echo 'WPEWEBKIT_CONF_OPTS += -DWEBOS_MARK=webos-softfp-jit -DENABLE_JIT=ON -DENABLE_DFG_JIT=ON -DENABLE_FTL_JIT=OFF -DENABLE_C_LOOP=OFF -DENABLE_SAMPLING_PROFILER=OFF -DENABLE_WEBASSEMBLY=OFF -DUSE_LIBHYPHEN=OFF' >> package/wpewebkit/wpewebkit.mk
  # WEBKIT_MCPU=cortex-a55 compiles WebKit (only) for the C1's real cores instead of buildroot-nc4's
  # cortex-a9: same softfp ABI, but hardware integer divide for the JIT and newer scheduling. The
  # wrapper's own -mcpu comes first, so this one wins.
  [ -z \"\$MCPU_LINE\" ] || echo \"\$MCPU_LINE\" >> package/wpewebkit/wpewebkit.mk
  # buildroot-nc4 pins WebKit 2.50.5; 2.52 brings faster async scrolling and text rendering plus
  # crash fixes. The patches in /src/patches target 2.52.6 (the 2.50.5 set is in patches-2.50.5).
  sed -i 's/^WPEWEBKIT_VERSION = .*/WPEWEBKIT_VERSION = 2.52.6/' package/wpewebkit/wpewebkit.mk
  grep -q 'wpewebkit-2.52.6.tar.xz' package/wpewebkit/wpewebkit.hash || \
    echo 'sha256  b2bafef2751625b7fdf530f230ff0f542ff0eeba3590c3a989d931b2a55c858e  wpewebkit-2.52.6.tar.xz' >> package/wpewebkit/wpewebkit.hash
  sed -i 's/^BR2_JLEVEL=.*/BR2_JLEVEL=6/' .config 2>/dev/null || true
  if [ ! -f .config ]; then
    make -s webos_tv_defconfig
    cat /src/wpe.fragment >> .config
    make -s olddefconfig
  fi
  grep -E '^BR2_(ARM_INSTRUCTIONS|PACKAGE_WPEWEBKIT|PACKAGE_WPEBACKEND|PACKAGE_GST1_LIBAV)' .config
  make $*
"
