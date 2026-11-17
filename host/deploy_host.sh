#!/bin/sh
# Rebuilds only the host binary (main.c) and swaps it into the app installed on the TV.
# For WebKit or bundle changes use bundle.sh + make_ipk.py and a full install instead.
# usage: browser/host/deploy_host.sh <tv-ip>
set -eu
TV=$1
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)
OUT="$ROOT/build/hostonly"
# SDL2-webOS 2.30.12 (lib/ + include/): buildroot's SDL2 has no Wayland driver. See host/README.md.
SDL_PKG=${SDL_PKG:-$ROOT/../sdlpkg}
APPDIR=/media/developer/apps/usr/palm/applications/com.viiees.browser
mkdir -p "$OUT"
docker run --rm -v wpe-br:/work -v "$HERE":/src:ro -v "$SDL_PKG":/sdl:ro -v "$OUT":/out wpe-br sh -euc '
  export PATH=/work/buildroot/output/host/bin:$PATH
  arm-webos-linux-gnueabi-gcc -O2 -Wall -o /out/browser /src/main.c -I/sdl/include/SDL2 -I/sdl/include \
    $(pkg-config --cflags --libs wpe-webkit-2.0 wpebackend-fdo-1.0 sdl2 egl glesv2 glib-2.0) \
    -Wl,--disable-new-dtags -Wl,-rpath,\$ORIGIN/lib
  arm-webos-linux-gnueabi-strip /out/browser'
RESULT=$(python3 "$HERE/tvstream.py" "$TV" "$OUT/browser" /media/developer/temp/browser.new | tail -n 1)
echo "$RESULT"
# A failed upload must not replace the installed binary (a full disk once left it empty).
[ "$RESULT" = "md5 ok" ] || exit 1
python3 "$ROOT/bench/tvtelnet.py" "$TV" \
  "chmod 755 /media/developer/temp/browser.new && mv /media/developer/temp/browser.new $APPDIR/browser"
