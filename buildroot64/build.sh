#!/bin/sh
# Builds a 64-bit (aarch64) WPE WebKit for the C1 with upstream buildroot inside Docker.
# The TV runs an aarch64 kernel under a 32-bit userspace, so the bundle carries its own glibc and
# ld-linux-aarch64 (kernel headers pinned to 4.4: glibc refuses to start on a kernel older than
# the headers it was built against). There is no 64-bit Mali driver: GL comes from Mesa llvmpipe
# here, or from webosbrew/webos-bridge-64to32 forwarding to the TV's 32-bit libEGL at run time.
# Same WebKit version as the 32-bit build (2.52.6) so A/B differs only in the word size.
# The tree lives in the "wpe-br64" volume, next to the 32-bit "wpe-br".
# usage: browser/buildroot64/build.sh [make target...]
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
BR_REF=2026.08.1

docker build -q -t wpe-br "$HERE/../buildroot" >/dev/null
docker run --rm -v wpe-br64:/work -v "$HERE":/src:ro wpe-br sh -euc "
  if [ ! -d /work/buildroot ]; then
    git clone -q --depth 1 --branch $BR_REF https://github.com/buildroot/buildroot.git /work/buildroot
  fi
  cd /work/buildroot
  sed -i 's/^WPEWEBKIT_VERSION = .*/WPEWEBKIT_VERSION = 2.52.6/' package/wpewebkit/wpewebkit.mk
  grep -q 'wpewebkit-2.52.6.tar.xz' package/wpewebkit/wpewebkit.hash || \
    echo 'sha256  b2bafef2751625b7fdf530f230ff0f542ff0eeba3590c3a989d931b2a55c858e  wpewebkit-2.52.6.tar.xz' >> package/wpewebkit/wpewebkit.hash
  sed -i '/webos-aarch64/d' package/wpewebkit/wpewebkit.mk
  echo 'WPEWEBKIT_CONF_OPTS += -DWEBOS_MARK=webos-aarch64 -DENABLE_JIT=ON -DENABLE_DFG_JIT=ON -DENABLE_FTL_JIT=ON -DENABLE_WEBASSEMBLY=ON -DUSE_LIBHYPHEN=OFF -DENABLE_WPE_PLATFORM=ON -DENABLE_WPE_PLATFORM_DRM=OFF -DENABLE_MINIBROWSER=ON' >> package/wpewebkit/wpewebkit.mk
  if [ ! -f .config ]; then
    cp /src/defconfig .config
    make -s olddefconfig
  fi
  # Kernel 4.4 headers lack linux/dma-buf.h, which WebKit's GBM code includes (see include/).
  S=output/host/aarch64-buildroot-linux-gnu/sysroot/usr/include/linux
  [ -d "\$S" ] && [ ! -e "\$S/dma-buf.h" ] && cp /src/include/linux/dma-buf.h "\$S/"
  grep -E '^BR2_(aarch64|cortex|PACKAGE_HOST_LINUX_HEADERS_CUSTOM|PACKAGE_WPEWEBKIT|PACKAGE_MESA3D_GALLIUM)' .config
  make $*
"
