#!/bin/sh
# Target sysroot for chromium120: Debian buster armel. buster has glibc 2.28, the same as the C1,
# so binaries run on the TV's own libc. armel is soft-float EABI, link-compatible with the TV's
# softfp userspace (same core-register calling convention).
# debootstrap --foreign only unpacks the .debs (nothing ARM gets executed). Absolute symlinks are
# made relative so they resolve inside the sysroot.
# usage: browser/cr120/sysroot.sh   (runs in the cr120 image, writes cr120:/w/sysroot)
set -eu
PKGS=libc6-dev,linux-libc-dev,libgcc-8-dev,libstdc++-8-dev,libnss3-dev,libnspr4-dev,\
libfontconfig1-dev,libfreetype6-dev,libexpat1-dev,libxkbcommon-dev,libwayland-dev,libdrm-dev,\
libglib2.0-dev,libffi-dev,zlib1g-dev,libpcre3-dev,libudev-dev,libpci-dev,libasound2-dev,\
libdbus-1-dev,libegl1-mesa-dev,libgles2-mesa-dev,libgbm-dev
NDK=$(cd "$(dirname "$0")/../../toolchain/arm-webos-linux-gnueabi_sdk-buildroot/arm-webos-linux-gnueabi/sysroot" && pwd)
docker run --rm -v cr120:/w -v "$NDK":/ndk:ro cr120 sh -euc "
  if [ ! -f /w/sysroot/.done ]; then
    rm -rf /w/sysroot
    debootstrap --foreign --no-check-gpg --arch=armel --variant=minbase --include=$PKGS \
      buster /w/sysroot http://archive.debian.org/debian
    # --foreign leaves --include packages in the apt cache for the second stage; unpack them all.
    for d in /w/sysroot/var/cache/apt/archives/*.deb; do dpkg-deb -x \"\$d\" /w/sysroot; done
    find /w/sysroot -type l -lname '/*' | while read -r l; do
      t=\$(readlink \"\$l\"); ln -snf \"\$(realpath -m --relative-to=\"\$(dirname \"\$l\")\" \"/w/sysroot\$t\")\" \"\$l\"
    done
    touch /w/sysroot/.done
  fi
  # wl_webos_shell client (the only shell the C1 compositor displays) from the webOS NDK sysroot;
  # the TV ships the same libwayland-webos-client.so.1.
  mkdir -p /w/sysroot/usr/lib/pkgconfig
  # Chromium's pkg-config.py looks only in usr/lib/pkgconfig and usr/share/pkgconfig.
  for pc in /w/sysroot/usr/lib/arm-linux-gnueabi/pkgconfig/*.pc; do
    ln -snf ../arm-linux-gnueabi/pkgconfig/\$(basename \$pc) /w/sysroot/usr/lib/pkgconfig/
  done
  cp /ndk/usr/include/wayland-webos-*-client-protocol.h /w/sysroot/usr/include/
  cp -P /ndk/usr/lib/libwayland-webos-client.so* /w/sysroot/usr/lib/
  # The TV runs libwayland 1.11 (buster has 1.16): build against the NDK's client headers and
  # library so no newer symbol gets linked. text-client is the webOS text-input protocol.
  for h in wayland-client wayland-client-core wayland-client-protocol wayland-util wayland-version \
           wayland-cursor wayland-text-client-protocol; do
    cp /ndk/usr/include/\$h.h /w/sysroot/usr/include/
  done
  # webos_text_input.cc takes KEY_* from <curses.h>, as on the OE build (only macros are used).
  cp /ndk/usr/include/curses.h /ndk/usr/include/ncurses_dll.h /ndk/usr/include/unctrl.h /w/sysroot/usr/include/
  # The NDK's libwayland-client wants libffi.so.8 (the TV's own one uses libffi.so.6). Only the
  # build-time run of v8_context_snapshot_generator under qemu loads it.
  cp -P /ndk/usr/lib/libwayland-client.so* /ndk/usr/lib/libwayland-cursor.so* /ndk/usr/lib/libffi.so.8* \
    /w/sysroot/usr/lib/arm-linux-gnueabi/
  printf 'prefix=/usr\nlibdir=/usr/lib\nincludedir=/usr/include\nName: wayland-webos-client\nDescription: webOS wayland extensions\nVersion: 1.0.0\nRequires: wayland-client\nLibs: -L\${libdir} -lwayland-webos-client\nCflags:\n' > /w/sysroot/usr/lib/pkgconfig/wayland-webos-client.pc
  # pkg-config does not drop <sysroot>/usr/include as a system dir, and such a flag lands before
  # libc++'s headers (<cmath> then finds glibc's math.h). Remove bare -I\${includedir} tokens.
  # Only where includedir is plain /usr/include (nss.pc, for one, points it at /usr/include/nss).
  # Re-unpack the .pc files first so this edit is idempotent.
  for d in /w/sysroot/var/cache/apt/archives/*.deb; do
    dpkg-deb --fsys-tarfile \"\$d\" | tar -x -C /w/sysroot --wildcards '*.pc' 2>/dev/null || true
  done
  grep -l -x 'includedir=\${prefix}/include' /w/sysroot/usr/lib/pkgconfig/*.pc /w/sysroot/usr/share/pkgconfig/*.pc | \
    xargs sed -i --follow-symlinks -e 's/-I\${includedir}\( \|\$\)/\1/g'
  # Chromium's clang --target and pkg-config.py use the armhf multiarch name for every arm build.
  # The ABI itself comes from -mfloat-abi=softfp, so alias the armel dirs.
  ln -snf arm-linux-gnueabi /w/sysroot/lib/arm-linux-gnueabihf
  ln -snf arm-linux-gnueabi /w/sysroot/usr/lib/arm-linux-gnueabihf
  ln -snf arm-linux-gnueabi /w/sysroot/usr/include/arm-linux-gnueabihf
  ln -snf arm-linux-gnueabi /w/sysroot/usr/lib/gcc/arm-linux-gnueabihf
  ls /w/sysroot/usr/lib/arm-linux-gnueabi | wc -l
  ls /w/sysroot/lib/arm-linux-gnueabi/libc-*
"
