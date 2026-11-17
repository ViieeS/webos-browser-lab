#!/bin/sh
# Runs inside the wpe-br container: compiles the host and gathers everything it loads into /out/app.
# Libraries the TV already has are left out: glibc must match the TV's, and EGL/GLES/Wayland must be
# the vendor's own (EGL_WL_bind_wayland_display only works with the libwayland-server the driver uses).
# The app dir comes last in the TV's LD_LIBRARY_PATH, so every ELF gets a DT_RPATH to the bundle.
set -eu
BR=/work/buildroot/output
T=$BR/target
SYSROOT=$BR/staging
OUT=/out/app
PATCHELF=$BR/host/bin/patchelf
READELF=$BR/host/bin/arm-webos-linux-gnueabi-readelf
# libwayland-egl.so: buildroot's stub shadows the vendor one and eglCreateWindowSurface fails BAD_ALLOC.
# libxkbcommon.so.0: the newer one rejects LG's keymap (keycodes above 0xfff).
SKIP=' ld-linux.so.3 libc.so.6 libm.so.6 libpthread.so.0 libdl.so.2 librt.so.1 libresolv.so.2 libutil.so.1
 libEGL.so.1 libGLESv2.so.2 libwayland-client.so.0 libwayland-server.so.0 libwayland-egl.so.1
 libwayland-egl.so libxkbcommon.so.0 libSDL2-2.0.so.0 '
# buildroot's SDL2 has no Wayland video driver; /sdl is the SDL2-webOS build the launcher ships.
# Compile against its headers too: buildroot's add a webOS inputSource field to key and text events
# unconditionally, SDL2-webOS only under SDL_WEBOS_BROKEN_ABI, so mixing them shifts event fields.
SDL_LIB=/sdl/lib/libSDL2-2.0.so.0

rm -rf "$OUT"
mkdir -p "$OUT/lib" "$OUT/libexec" "$OUT/lib/gstreamer-1.0" "$OUT/lib/gio/modules"
export PATH="$BR/host/bin:$PATH"
arm-webos-linux-gnueabi-gcc -O2 -Wall -o "$OUT/browser" /src/main.c -I/sdl/include/SDL2 -I/sdl/include \
  $(pkg-config --cflags --libs wpe-webkit-2.0 wpebackend-fdo-1.0 sdl2 egl glesv2 glib-2.0) \
  -Wl,--disable-new-dtags -Wl,-rpath,'$ORIGIN/lib'

cp "$T"/usr/libexec/wpe-webkit-2.0/WPEWebProcess "$T"/usr/libexec/wpe-webkit-2.0/WPENetworkProcess "$OUT/libexec/"
cp "$T"/usr/lib/gstreamer-1.0/*.so "$OUT/lib/gstreamer-1.0/"
cp "$T"/usr/lib/gio/modules/*.so "$OUT/lib/gio/modules/"
cp -L "$T"/usr/lib/libWPEBackend-fdo-1.0.so.1 "$OUT/lib/"        # dlopen'ed by libwpe, not NEEDED
cp -L "$SDL_LIB" "$OUT/lib/libSDL2-2.0.so.0"
# The host preloads it into WebKit's processes (see use_bundle); built by browser/mimalloc/build_mimalloc.sh.
[ -e /work/mimalloc-build/libmimalloc.so.2 ] || { echo "missing mimalloc: run browser/mimalloc/build_mimalloc.sh" >&2; exit 1; }
arm-webos-linux-gnueabi-strip -o "$OUT/lib/libmimalloc.so.2" /work/mimalloc-build/libmimalloc.so.2
[ -d "$T/usr/lib/wpe-webkit-2.0" ] && cp -r "$T/usr/lib/wpe-webkit-2.0" "$OUT/lib/"
cp /src/bench.html "$OUT/"
mkdir -p "$OUT/etc/fonts"
cp /src/fonts.conf "$OUT/etc/fonts/"
mkdir -p "$OUT/etc/ssl/certs"
cp -L "$T/etc/ssl/certs/ca-certificates.crt" "$OUT/etc/ssl/certs/"

find_lib() {
  for d in "$T/usr/lib" "$T/lib" "$SYSROOT/usr/lib" "$SYSROOT/lib"; do
    [ -e "$d/$1" ] && { echo "$d/$1"; return; }
  done
  echo "missing: $1" >&2
  exit 1
}

# Breadth-first over DT_NEEDED until no new library appears.
queue=$(find "$OUT" -type f \( -name '*.so*' -o -perm -u+x \) ! -name '*.crt')
while [ -n "$queue" ]; do
  next=
  for f in $queue; do
    for n in $("$READELF" -d "$f" 2>/dev/null | sed -n 's/.*(NEEDED).*\[\(.*\)\]/\1/p'); do
      case "$SKIP" in *" $n "*) continue ;; esac
      [ -e "$OUT/lib/$n" ] && continue
      cp -L "$(find_lib "$n")" "$OUT/lib/$n"
      next="$next $OUT/lib/$n"
    done
  done
  queue=$next
done

"$PATCHELF" --force-rpath --set-rpath '$ORIGIN/../lib' "$OUT"/libexec/*
for f in "$OUT"/lib/*.so*; do "$PATCHELF" --force-rpath --set-rpath '$ORIGIN' "$f"; done
for f in "$OUT"/lib/gstreamer-1.0/*.so "$OUT"/lib/gio/modules/*.so; do
  "$PATCHELF" --force-rpath --set-rpath '$ORIGIN/..' "$f"
done
find "$OUT" -type f \( -name '*.so*' -o -perm -u+x \) ! -name '*.crt' -exec arm-webos-linux-gnueabi-strip --strip-unneeded {} +
du -sh "$OUT"
ls "$OUT/lib" | wc -l
