# Build image for webOS OSE chromium120 on the colima aarch64 VM.
# The repo's prebuilt clang/gn/ninja are x86_64, so the image brings native arm64 ones.
# qemu-user-static runs the 32-bit ARM host tools V8 needs (mksnapshot, torque): Apple silicon
# cannot execute AArch32.
FROM ubuntu:24.04
RUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
      clang-18 lld-18 llvm-18 libclang-rt-18-dev ninja-build python3 python3-setuptools \
      git curl ca-certificates pkg-config gperf bison flex nodejs debootstrap qemu-user-static \
      xz-utils file patchelf rsync binutils-arm-linux-gnueabi && \
    rm -rf /var/lib/apt/lists/*
RUN for t in clang clang++ lld ld.lld llvm-ar llvm-nm llvm-objcopy llvm-readelf llvm-strip llvm-objdump; do \
      ln -sf /usr/bin/$t-18 /usr/local/bin/$t; done
# Host-toolchain deps. Chromium's pkg-config.py only searches <sysroot>/usr/lib/pkgconfig, and the
# host sysroot is "/", so expose the multiarch .pc files there.
RUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq libglib2.0-dev \
      libnss3-dev libnspr4-dev libxkbcommon-dev libwayland-dev libfontconfig-dev libfreetype-dev \
      libexpat1-dev libdbus-1-dev libudev-dev libpci-dev libasound2-dev zlib1g-dev libdrm-dev && \
    rm -rf /var/lib/apt/lists/* && mkdir -p /usr/lib/pkgconfig && \
    ln -sf /usr/lib/aarch64-linux-gnu/pkgconfig/*.pc /usr/lib/pkgconfig/ && \
    grep -l -x 'includedir=${prefix}/include' /usr/lib/pkgconfig/*.pc /usr/share/pkgconfig/*.pc | \
      xargs sed -i --follow-symlinks -e 's/-I${includedir}\( \|$\)/\1/g'
# A bare -I/usr/include from a .pc would precede libc++'s headers (see sysroot.sh).
WORKDIR /w
