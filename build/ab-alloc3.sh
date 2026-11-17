#!/bin/sh
# A/B/C of the bmalloc SystemHeap fix on the cortex-a9 build: the installed old lib (494d793b), the
# rebuild without patch 0013 (control for the rebuild itself), and 0013 v2 (malloc + offset word).
set -e
L=/media/developer/apps/usr/palm/applications/com.viiees.browser/lib
TVT=bench/tvtelnet.py
BENCH=./bench/bench.py
run() {
  python3 $TVT "$TV_HOST" "luna-send -n 1 luna://com.webos.applicationManager/closeByAppId '{\"id\":\"com.viiees.browser\"}' >/dev/null; sleep 2; pkill -9 -x browser; cp $L/libWPEWebKit.$1 $L/libWPEWebKit-2.0.so.1 && md5sum $L/libWPEWebKit-2.0.so.1"
  python3 $BENCH run --label "alloc-$1" micro load-wiki wheel-wiki speedometer
}
for round in 1 2 3; do
  run a9
  run a9nop
  run a9v2
done
