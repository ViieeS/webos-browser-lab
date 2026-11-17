#!/bin/sh
# Builds webOS OSE chromium120 for the C1 (armv7, softfp, glibc 2.28) in the cr120 image.
# Tree: cr120:/w/chromium120 (browser/cr120/fetch: git clone --depth 1), sysroot: cr120:/w/sysroot
# (sysroot.sh), gn: cr120:/w/gn/out/gn. Patches in browser/cr120/patches/*.patch apply once
# (marker file per patch).
# usage: browser/cr120/build.sh gen          -> gn gen out/c1 from args.gn
#        browser/cr120/build.sh <ninja targets...>
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
JOBS=${JOBS:-10}
docker run --rm -v cr120:/w -v "$HERE":/src:ro -e JOBS="$JOBS" \
  -e WAYLAND_SCANNER=/w/wlscanner/x/usr/bin/wayland-scanner cr120 sh -euc '
  cd /w/chromium120/src
  # Host tools are native arm64 and build against the container root.
  ln -snf / build/linux/debian_bullseye_arm64-sysroot
  # third_party/node ships an x86_64 node; the build scripts call it by that path.
  mkdir -p third_party/node/linux/node-linux-x64/bin
  ln -snf /usr/bin/node third_party/node/linux/node-linux-x64/bin/node
  # Same for devtools-frontend esbuild (0.14.13, as pinned in its DEPS).
  cp /src/tools/esbuild third_party/devtools-frontend/src/third_party/esbuild/esbuild
  # Files the OSE snapshot dropped (test data) but content_shell still references, taken from
  # upstream 120.0.6099.269.
  cp -ru /src/extra/. .   # -u: an edited overlay file replaces the tree copy, others keep mtime
  for p in /src/patches/*.patch; do
    [ -e "$p" ] || continue
    m=/w/applied.$(basename "$p")
    [ -f "$m" ] || { patch -p1 --forward < "$p"; touch "$m"; }
  done
  if [ "$1" = gen ]; then
    mkdir -p out/c1 && cp /src/args.gn out/c1/args.gn
    /w/gn/out/gn gen out/c1
  else
    ninja -C out/c1 -j "$JOBS" "$@"
  fi
' sh "$@"
