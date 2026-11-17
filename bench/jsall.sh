#!/bin/sh
# Every JetStream-lite test (the JS groups that fit in the TV's memory) as its own jsc process, in
# each mode, one line per run: "JSALL <mode> <test> score=<pts> wall_s=<s> peak_rss_kb=<kb> rc=<rc>".
# Run detached on the TV (tvtelnet stops at 180 s): nohup jsall.sh > /tmp/jsall.txt 2>&1 &
TESTS="Air Basic ML Babylon cdjs first-inspector-code-load multi-inspector-code-load Box2D octane-code-load crypto delta-blue earley-boyer gbemu mandreel navier-stokes pdfjs raytrace regexp-octane hash-map doxbee-promise doxbee-async ai-astar gaussian-blur stanford-crypto-aes stanford-crypto-pbkdf2 stanford-crypto-sha256 json-stringify-inspector json-parse-inspector bigint-noble-ed25519 proxy-mobx"
MODES=${MODES:-"32 64 64sys"}
for t in $TESTS; do
  for m in $MODES; do
    OUT=$(/media/developer/temp/jsrun.sh "$m" "$t")
    SCORE=$(echo "$OUT" | grep '^Overall Score' | awk '{print $3}')
    echo "JSALL $m $t score=${SCORE:-none} $(echo "$OUT" | grep '^JSRUN' | cut -d' ' -f2-)"
  done
done
echo "JSALL done"
