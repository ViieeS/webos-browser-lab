#!/bin/sh
# Builds mimalloc as a shared library for the C1 (armv7 softfp) with the buildroot-nc4 toolchain in
# the wpe-br volume. The host preloads it into WebKit's processes: with env Malloc=1 bmalloc hands
# every allocation to the system malloc, so this swaps glibc's allocator without rebuilding WebKit.
# usage: browser/mimalloc/build_mimalloc.sh   ->  browser/build/libmimalloc.so.2
set -eu
VERSION=2.1.7
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=$(cd "$HERE/../build" && pwd)
docker run --rm -v wpe-br:/work -v "$OUT":/out wpe-br sh -euc "
  cd /work
  if [ ! -d mimalloc-$VERSION ]; then
    wget -q -O mimalloc.tar.gz https://github.com/microsoft/mimalloc/archive/refs/tags/v$VERSION.tar.gz
    tar xzf mimalloc.tar.gz
    rm mimalloc.tar.gz
  fi
  rm -rf mimalloc-build
  mkdir mimalloc-build
  cd mimalloc-build
  export PATH=/work/buildroot/output/host/bin:\$PATH
  cmake -G Ninja ../mimalloc-$VERSION \
    -DCMAKE_TOOLCHAIN_FILE=/work/buildroot/output/host/share/buildroot/toolchainfile.cmake \
    -DCMAKE_BUILD_TYPE=Release -DMI_BUILD_TESTS=OFF -DMI_BUILD_STATIC=OFF -DMI_BUILD_OBJECT=OFF \
    -DMI_SECURE=OFF -DMI_OVERRIDE=ON -DMI_INSTALL_TOPLEVEL=ON > /out/mimalloc-build.log 2>&1
  ninja >> /out/mimalloc-build.log 2>&1 || { tail -n 30 /out/mimalloc-build.log; exit 1; }
  arm-webos-linux-gnueabi-strip -o /out/libmimalloc.so.2 \$(ls libmimalloc.so.2.* | head -n 1)
  ls -la /out/libmimalloc.so.2
"
