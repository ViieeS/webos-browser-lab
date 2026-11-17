#!/bin/sh
# Packs content_shell and its runtime files into browser/cr120/cr120.tar.gz for
# /media/developer/temp/cr120 on the TV. The binary runs on the TV's own glibc 2.28 loader, so only
# the libraries the TV lacks (tv_libs.txt: `ls /lib /usr/lib` on the TV) go into lib/, taken from
# the buster sysroot. EGL/GLES are dlopened by name and come from the TV (Mali).
# usage: browser/cr120/bundle.sh   then upload with browser/host/tvstream.py and untar on the TV
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
docker run --rm -v cr120:/w -v "$HERE":/src -v "$HERE/../host":/host:ro cr120 sh -euc '
  O=/w/chromium120/src/out/c1
  B=/w/bundle/cr120
  rm -rf /w/bundle && mkdir -p $B/lib
  llvm-strip -o $B/content_shell $O/content_shell
  cd $O
  for f in *.pak icudtl.dat snapshot_blob.bin v8_context_snapshot.bin; do
    [ -e "$f" ] && cp "$f" $B/
  done
  for d in locales neva_locales; do
    [ -d "$d" ] && cp -r "$d" $B/
  done
  cp /host/fonts.conf $B/
  queue=$B/content_shell
  while [ -n "$queue" ]; do
    next=
    for f in $queue; do
      for n in $(llvm-readelf -d "$f" | sed -n "s/.*(NEEDED).*\[\(.*\)\]/\1/p"); do
        grep -qx "$n" /src/tv_libs.txt && continue
        [ -e $B/lib/$n ] && continue
        p=$(find /w/sysroot/lib/arm-linux-gnueabi /w/sysroot/usr/lib/arm-linux-gnueabi /w/sysroot/usr/lib -maxdepth 1 -name "$n" | head -1)
        [ -n "$p" ] || { echo "missing: $n" >&2; exit 1; }
        cp -L "$p" $B/lib/$n
        echo "bundled $n"
        next="$next $B/lib/$n"
      done
    done
    queue=$next
  done
  # wl_egl_window is private to the libwayland-egl + EGL pair: use the Mali one from the TV under
  # the buster soname. The client calls only the wl_egl_window_* functions.
  ln -sf /usr/lib/libwayland-egl.so.0 $B/lib/libwayland-egl.so.1
  du -sh $B
  tar -C /w/bundle -czf /src/cr120.tar.gz cr120
'
ls -la "$HERE/cr120.tar.gz"
