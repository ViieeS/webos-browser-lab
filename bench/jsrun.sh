#!/bin/sh
# Runs JetStream 3 tests in a jsc shell on the TV and prints the score lines, wall time and peak RSS.
# Shell runs keep the browser (layout, paint, IPC) out, so 32- vs 64-bit differ only in JSC itself.
# usage: jsrun.sh <32|32rx|64|64own|64sys> <test[,test...]>   (64sys: 64-bit with Malloc=1 like the 32-bit browser)
J64=/media/developer/temp/jsc64
case "$1" in
  32) set -- "$2"; RUN="env Malloc=1 LD_LIBRARY_PATH=/media/developer/apps/usr/palm/applications/com.viiees.browser/lib /media/developer/temp/jsc32/jsc" ;;
  32rx) set -- "$2"; RUN="env Malloc=1 LD_LIBRARY_PATH=/media/developer/apps/usr/palm/applications/com.viiees.browser/lib /media/developer/temp/jsc32/jsc --useRegExpJIT=true" ;;
  64own) set -- "$2"; D=/media/developer/temp/jsc64own; RUN="$D/ld-linux-aarch64.so.1 --library-path $D $D/jsc --useRegExpJIT=true" ;;
  64) set -- "$2"; RUN="$J64/lib/ld-linux-aarch64.so.1 --library-path $J64/lib $J64/jsc" ;;
  64sys) set -- "$2"; RUN="env Malloc=1 $J64/lib/ld-linux-aarch64.so.1 --library-path $J64/lib $J64/jsc" ;;
  *) echo "usage: jsrun.sh <32|32rx|64|64own|64sys> <tests>"; exit 2 ;;
esac
cd /media/developer/bench/jetstream3.0 || exit 1
T0=$(date +%s)
$RUN cli.js -- --no-prefetch "--test=$1" > /tmp/jsrun.out 2>&1 &
P=$!
HWM=0
while kill -0 $P 2>/dev/null; do
  H=$(grep VmHWM /proc/$P/status 2>/dev/null | awk '{print $2}')
  [ -n "$H" ] && HWM=$H
  sleep 1
done
wait $P
RC=$?
grep -iE 'score|error|exception|fail' /tmp/jsrun.out | grep -v '^ *$' | tail -n 80
echo "JSRUN rc=$RC wall_s=$(( $(date +%s) - T0 )) peak_rss_kb=$HWM"
