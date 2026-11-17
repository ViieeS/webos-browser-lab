#!/bin/sh
# Loads <uri> into uMediaServer as appId com.webos.app.1 with payload option <json> (default minimal),
# plays it and prints 6 s of events: does this uri/option play from luna?
# usage on the TV: sh ums_http.sh <uri> ['<option json>']
OPT=${2:-'{"appId":"com.webos.app.1"}'}
R=$(luna-send -n 1 luna://com.webos.media/load "{\"uri\":\"$1\",\"type\":\"media\",\"payload\":{\"option\":$OPT}}")
ID=$(echo "$R" | sed -n 's/.*"mediaId":"\([^"]*\)".*/\1/p')
[ -n "$ID" ] || { echo "load failed: $R"; exit 1; }
luna-send -n 1 luna://com.webos.media/notifyForeground "{\"mediaId\":\"$ID\"}" > /dev/null
luna-send -n 1 luna://com.webos.media/play "{\"mediaId\":\"$ID\"}" > /dev/null
luna-send -w 6000 -i luna://com.webos.media/subscribe "{\"mediaId\":\"$ID\"}" | grep -v '^$' | cut -c1-160 | grep -v bufferRange | head -n 40
luna-send -n 1 luna://com.webos.media/unload "{\"mediaId\":\"$ID\"}" > /dev/null
