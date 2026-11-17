#!/bin/sh
# Plays one clip through com.webos.media (uMediaServer) for 10 s and prints whether time advances
# and how much CPU the media pipeline used: tells hardware decode from software without a browser.
# usage: ums_probe.sh <file in /media/developer/bench/media>
F=/media/developer/bench/media/$1
ID=$(luna-send -n 1 luna://com.webos.media/load "{\"uri\":\"file://$F\",\"type\":\"media\",\"payload\":{\"option\":{\"appId\":\"${APPID:-com.webos.app.browser}\",\"windowId\":\"\"}}}" | sed -n 's/.*"mediaId":"\([^"]*\)".*/\1/p')
[ -n "$ID" ] || { echo "$1: load failed"; exit 1; }
luna-send -n 1 luna://com.webos.media/play "{\"mediaId\":\"$ID\"}" > /dev/null
sleep 2
cpu() {
  t=0
  for p in $(grep -l starfish-media /proc/[0-9]*/comm 2>/dev/null | cut -d/ -f3); do
    set -- $(cut -d' ' -f14,15 /proc/$p/stat)
    t=$((t + $1 + $2))
  done
  echo $t
}
A=$(cpu)
sleep 10
B=$(cpu)
EV=$(luna-send -n 4 -w 4000 luna://com.webos.media/subscribe "{\"mediaId\":\"$ID\"}" 2>&1 | tr -d ' \n')
T=$(echo "$EV" | sed -n 's/.*"currentTime":\([0-9]*\).*/\1/p')
VI=$(echo "$EV" | grep -o '"videoInfo":{[^}]*}' | head -n 1)
ER=$(echo "$EV" | grep -o '"error":{[^}]*}' | head -n 1)
RES=$(luna-send -n 1 luna://com.webos.media/getActivePipelines '{}' | tr -d ' \n' | sed 's/},{"window_group_id/\n/g' | grep "\"id\":\"$ID\"" | grep -o '"resource":"[A-Z0-9_]*"' | sort -u | cut -d'"' -f4 | tr '\n' ',')
STATE=$(luna-send -n 1 luna://com.webos.media/getActivePipelines '{}' | tr -d ' \n' | sed 's/},{"window_group_id/\n/g' | grep "\"id\":\"$ID\"" | grep -o '"mediaState":"[a-z]*"')
luna-send -n 1 luna://com.webos.media/unload "{\"mediaId\":\"$ID\"}" > /dev/null
echo "$1: $STATE resources=$RES pipeline_cpu_10s=$((B - A)) $ER"
