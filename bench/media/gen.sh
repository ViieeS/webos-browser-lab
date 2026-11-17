#!/bin/sh
# Generates the synthetic video set for pages/video.html: 20 s of moving test pattern in the codecs
# and sizes streaming apps use, so playback is tested without downloading anything.
# usage: browser/bench/media/gen.sh   ->  browser/build/media/*.{mp4,webm}
set -eu
OUT=${OUT:-$(cd "$(dirname "$0")/../.." && pwd)/build/media}
mkdir -p "$OUT"
src() { echo "testsrc2=size=$1:rate=$2,format=yuv420p"; }
enc() {   # name, size, rate, codec args...
  name=$1 size=$2 rate=$3
  shift 3
  [ -s "$OUT/$name" ] || ffmpeg -hide_banner -loglevel error -y -f lavfi -t 20 -i "$(src "$size" "$rate")" "$@" "$OUT/$name"
}
enc h264-1080p30.mp4 1920x1080 30 -c:v libx264 -preset veryfast -b:v 8M -profile:v high -movflags +faststart
enc h264-1080p60.mp4 1920x1080 60 -c:v libx264 -preset veryfast -b:v 12M -profile:v high -movflags +faststart
enc hevc-2160p30.mp4 3840x2160 30 -c:v libx265 -preset fast -b:v 15M -tag:v hvc1 -movflags +faststart
enc vp9-1080p60.webm 1920x1080 60 -c:v libvpx-vp9 -deadline realtime -cpu-used 8 -b:v 8M -row-mt 1
enc vp9-2160p30.webm 3840x2160 30 -c:v libvpx-vp9 -deadline realtime -cpu-used 8 -b:v 18M -row-mt 1
enc av1-1080p30.mp4 1920x1080 30 -c:v libsvtav1 -preset 10 -b:v 5M -movflags +faststart
ls -la "$OUT"
