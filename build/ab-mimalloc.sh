#!/bin/sh
# A/B: glibc malloc vs mimalloc preloaded into WebKit's processes (bmalloc forwards to the system
# malloc under the host's Malloc=1). Same lib (a55cssjit) for both; only the launch env differs.
set -e
BENCH=./bench/bench.py
MI=LD_PRELOAD=/media/developer/apps/usr/palm/applications/com.viiees.browser/lib/libmimalloc.so.2
CASES="micro load-wiki raf-wiki speedometer cold-youtube wheel-wiki-settled"
for round in 1 2 3; do
  python3 $BENCH run --label mi-glibc $CASES
  python3 $BENCH run --label mi-mimalloc --p "env=$MI" $CASES
done
