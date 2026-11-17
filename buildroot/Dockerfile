FROM ubuntu:24.04
RUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
      build-essential cpio rsync bc libssl-dev unzip file wget python3 ruby gperf git \
      ca-certificates locales && \
    locale-gen en_US.UTF-8 && rm -rf /var/lib/apt/lists/*
ENV LANG=en_US.UTF-8 FORCE_UNSAFE_CONFIGURE=1
WORKDIR /work
