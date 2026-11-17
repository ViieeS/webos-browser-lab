# Build image for WebOS-Chromium (Chromium 151, webOS-ports/chromium151) on the colima aarch64 VM.
# Chromium 151 ships clang (llvmorg-23-init) and Rust only for Linux x64 hosts, so the image brings native arm64 ones:
# clang/lld 23 from apt.llvm.org and a Rust nightly from the week of Chromium's pinned rustc. The build tree links them
# in at third_party/llvm-build/Release+Asserts and third_party/rust-toolchain (setup.sh), where GN and the
# upstream container scripts expect them.
# Ubuntu 22.04: the upstream sysroot scripts download jammy packages with apt.
FROM ubuntu:22.04
ARG LLVM=23
ARG RUST_NIGHTLY=nightly-2026-06-17
ARG NODE=v24.12.0
ARG NINJA=1.12.1
RUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
      ca-certificates curl wget gnupg lsb-release git python3 python3-pil zstd ccache cmake make unzip xz-utils file \
      patch rsync pkg-config gperf bison flex dpkg-dev binutils-arm-linux-gnueabi qemu-user-static libc6-dev g++ \
      libc6-armel-cross libgcc-s1-armel-cross libstdc++6-armel-cross && \
    rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://apt.llvm.org/llvm-snapshot.gpg.key | gpg --dearmor -o /usr/share/keyrings/llvm.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/llvm.gpg] http://apt.llvm.org/jammy/ llvm-toolchain-jammy-$LLVM main" \
      > /etc/apt/sources.list.d/llvm.list && \
    apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
      clang-$LLVM lld-$LLVM llvm-$LLVM libclang-$LLVM-dev libclang-rt-$LLVM-dev && \
    rm -rf /var/lib/apt/lists/* && \
    R=/usr/lib/llvm-$LLVM/lib/clang/$LLVM/lib && mkdir -p $R/aarch64-unknown-linux-gnu && \
    ln -s ../linux/libclang_rt.builtins-aarch64.a $R/aarch64-unknown-linux-gnu/libclang_rt.builtins.a
# Debian's compiler-rt uses the old lib/linux/<name>-<arch>.a layout; Chromium links the per-target one.
# Host-toolchain deps (host sysroot is "/"). Chromium's pkg-config.py only searches <sysroot>/usr/lib/pkgconfig.
# A bare -I${includedir} from a .pc would put /usr/include before libc++'s headers, so it is stripped.
RUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends libglib2.0-dev \
      libnss3-dev libnspr4-dev libxkbcommon-dev libwayland-dev libfontconfig-dev libfreetype-dev libexpat1-dev \
      libdbus-1-dev libudev-dev libasound2-dev zlib1g-dev libdrm-dev libpulse-dev && \
    rm -rf /var/lib/apt/lists/* && mkdir -p /usr/lib/pkgconfig && \
    ln -sf /usr/lib/aarch64-linux-gnu/pkgconfig/*.pc /usr/lib/pkgconfig/ && \
    grep -l -x 'includedir=${prefix}/include' /usr/lib/pkgconfig/*.pc /usr/share/pkgconfig/*.pc | \
      xargs sed -i --follow-symlinks -e 's/-I${includedir}\( \|$\)/\1/g'
RUN curl -fsSL "https://nodejs.org/dist/$NODE/node-$NODE-linux-arm64.tar.xz" | tar -xJ -C /opt && \
    mv /opt/node-$NODE-linux-arm64 /opt/node && \
    curl -fsSL -o /tmp/ninja.zip "https://github.com/ninja-build/ninja/releases/download/v$NINJA/ninja-linux-aarch64.zip" && \
    unzip -q /tmp/ninja.zip -d /usr/local/bin && rm /tmp/ninja.zip
ENV RUSTUP_HOME=/opt/rustup CARGO_HOME=/opt/cargo PATH=/opt/cargo/bin:/opt/node/bin:$PATH
RUN curl -fsSL https://sh.rustup.rs | sh -s -- -y -q --profile minimal --default-toolchain $RUST_NIGHTLY \
      --component rust-src --component rustfmt --target armv7-unknown-linux-gnueabi && \
    rustc --version
# bindgen for rust_bindgen_root (args.host.gn): bin/bindgen, bin/rustfmt, lib/libclang.so (clang 23's).
RUN cargo install -q --locked bindgen-cli && mkdir -p /opt/bindgen/bin /opt/bindgen/lib && \
    ln -s /opt/cargo/bin/bindgen /opt/bindgen/bin/bindgen && \
    ln -s "$(rustc --print sysroot)/bin/rustfmt" /opt/bindgen/bin/rustfmt && \
    ln -s /usr/lib/llvm-$LLVM/lib/libclang.so /opt/bindgen/lib/libclang.so && \
    ln -s "$(rustc --print sysroot)" /opt/rust-sysroot
# devtools-frontend runs esbuild from node_modules, which is an x86_64 binary: point its JS API at the arm64 build of
# the same version (third_party/devtools-frontend/src/node_modules/esbuild/package.json).
ARG ESBUILD=0.25.1
RUN mkdir -p /opt/esbuild && \
    curl -fsSL "https://registry.npmjs.org/@esbuild/linux-arm64/-/linux-arm64-$ESBUILD.tgz" | tar -xz -C /opt/esbuild && \
    /opt/esbuild/package/bin/esbuild --version
ENV ESBUILD_BINARY_PATH=/opt/esbuild/package/bin/esbuild
