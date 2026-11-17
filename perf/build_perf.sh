#!/bin/sh
# Builds a static `perf` for the C1 (armv7 softfp, kernel 4.4) from the 4.4 kernel tree with the
# buildroot-nc4 toolchain in the wpe-br volume. No libelf (elfutils does not build against this
# toolchain's kernel headers), so perf only records here; browser/perf/perfsym.py names the samples
# with addr2line on the unstripped libraries.
# usage: browser/perf/build_perf.sh   ->  browser/build/perf
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=$(cd "$HERE/../build" && pwd)
docker run --rm -v wpe-br:/work -v "$OUT":/out wpe-br sh -euc '
  cd /work
  if [ ! -d linux-4.4.302 ]; then
    wget -q https://cdn.kernel.org/pub/linux/kernel/v4.x/linux-4.4.302.tar.xz
    tar xJf linux-4.4.302.tar.xz
    rm linux-4.4.302.tar.xz
  fi
  export PATH=/work/buildroot/output/host/bin:$PATH
  cd linux-4.4.302/tools/perf
  # A 2016 tree with a 2026 compiler: warnings are not errors, and -fcommon for the old tentative
  # definitions. The NO_* knobs drop every optional library perf would look for.
  # The 4.4 generator copies versioned names (free@GLIBC_2.4) from the new nm into the linker
  # dynamic list, which ld rejects: the first link fails, the versions are stripped, the second links.
  M() {
    make -j8 ARCH=arm CROSS_COMPILE=arm-webos-linux-gnueabi- WERROR=0 LDFLAGS=-static \
    EXTRA_CFLAGS="-fcommon -Wno-error -Wno-implicit-function-declaration -Wno-int-conversion -Wno-incompatible-pointer-types -Wno-implicit-int -std=gnu11" \
    NO_LIBELF=1 NO_DWARF=1 NO_LIBUNWIND=1 NO_LIBPERL=1 NO_LIBPYTHON=1 NO_SLANG=1 NO_GTK2=1 \
    NO_LIBAUDIT=1 NO_LIBNUMA=1 NO_LIBBIONIC=1 NO_LIBCRYPTO=1 NO_BACKTRACE=1 NO_DEMANGLE=1 NO_LZMA=1 \
    NO_ZLIB=1 NO_LIBBABELTRACE=1 NO_AUXTRACE=1 "$@"
  }
  M > /out/perf-build.log 2>&1 || true
  sed -i "s/@[A-Z_0-9.]*;/;/" ../lib/traceevent/libtraceevent-dynamic-list
  M >> /out/perf-build.log 2>&1 || { tail -n 30 /out/perf-build.log; exit 1; }
  arm-webos-linux-gnueabi-strip -o /out/perf perf
  ls -la /out/perf
'
