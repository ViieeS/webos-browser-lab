#!/bin/sh
# Runs inside the wpe-br image with the wpe-br64 volume at /work: gathers the aarch64 MiniBrowser, the
# WebKit processes, Mesa (llvmpipe) and every library they load, glibc included, into /out/wpe64.
# The TV has no aarch64 loader, so every executable gets the bundle's ld-linux-aarch64 as its
# interpreter by absolute path: WebKit spawns its web and network processes by exec, not through us.
# usage (in the container): sh /src/bundle64.sh   ->  install the tree at $DEST on the TV
set -eu
DEST=/media/developer/temp/wpe64
BR=/work/buildroot/output
T=$BR/target
B=$BR/build/wpewebkit-2.52.6
OUT=/out/wpe64
RE=$BR/host/bin/aarch64-buildroot-linux-gnu-readelf
STRIP=$BR/host/bin/aarch64-buildroot-linux-gnu-strip
PATCHELF=$BR/host/bin/patchelf

rm -rf "$OUT"
mkdir -p "$OUT/bin" "$OUT/lib" "$OUT/libexec" "$OUT/lib/gstreamer-1.0" "$OUT/lib/gio/modules" "$OUT/etc/ssl/certs" "$OUT/etc/fonts"
cp "$B/bin/MiniBrowser" "$OUT/bin/"
cp "$T"/usr/libexec/wpe-webkit-2.0/WPEWebProcess "$T"/usr/libexec/wpe-webkit-2.0/WPENetworkProcess "$OUT/libexec/"
cp "$T"/usr/lib/gstreamer-1.0/*.so "$OUT/lib/gstreamer-1.0/"
cp "$T"/usr/lib/gio/modules/*.so "$OUT/lib/gio/modules/"
cp -L "$T"/lib/ld-linux-aarch64.so.1 "$OUT/lib/"
# libepoxy dlopens EGL/GLES (no DT_NEEDED), so Mesa's are listed by hand; their deps follow below.
cp -L "$T"/usr/lib/libEGL.so.1 "$T"/usr/lib/libGLESv2.so.2 "$T"/usr/lib/libgbm.so.1 "$OUT/lib/"
[ -d "$T/usr/lib/wpe-webkit-2.0" ] && cp -r "$T/usr/lib/wpe-webkit-2.0" "$OUT/lib/"
cp -L "$T/etc/ssl/certs/ca-certificates.crt" "$OUT/etc/ssl/certs/"
cp /host/fonts.conf "$OUT/etc/fonts/"
cp -L "$T/usr/share/wpe-webkit-2.0/inspector.gresource" "$OUT/" 2>/dev/null || true

find_lib() {
  for d in "$T/usr/lib" "$T/lib"; do
    [ -e "$d/$1" ] && { echo "$d/$1"; return; }
  done
  echo "missing: $1" >&2
  exit 1
}

queue=$(find "$OUT" -type f \( -name '*.so*' -o -perm -u+x \) ! -name '*.crt' ! -name '*.gresource')
while [ -n "$queue" ]; do
  next=
  for f in $queue; do
    for n in $("$RE" -d "$f" 2>/dev/null | sed -n 's/.*(NEEDED).*\[\(.*\)\]/\1/p'); do
      [ -e "$OUT/lib/$n" ] && continue
      cp -L "$(find_lib "$n")" "$OUT/lib/$n"
      next="$next $OUT/lib/$n"
    done
  done
  queue=$next
done

for f in "$OUT"/bin/* "$OUT"/libexec/*; do
  "$PATCHELF" --set-interpreter "$DEST/lib/ld-linux-aarch64.so.1" --force-rpath --set-rpath '$ORIGIN/../lib' "$f"
done
for f in "$OUT"/lib/*.so*; do
  case "$f" in */ld-linux-aarch64.so.1) continue ;; esac
  "$PATCHELF" --force-rpath --set-rpath '$ORIGIN' "$f"
done
for f in "$OUT"/lib/gstreamer-1.0/*.so "$OUT"/lib/gio/modules/*.so; do
  "$PATCHELF" --force-rpath --set-rpath '$ORIGIN/..' "$f"
done
find "$OUT" -type f \( -name '*.so*' -o -perm -u+x \) ! -name '*.crt' ! -name '*.gresource' ! -name 'ld-linux-aarch64.so.1' \
  -exec "$STRIP" --strip-unneeded {} +
du -sh "$OUT"
ls "$OUT/lib" | wc -l
