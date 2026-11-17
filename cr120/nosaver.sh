#!/bin/sh
# Keeps the TV screensaver off while benchmarks run: answers every tvpower screensaver request
# with ack=false, the way SDL-webOS does. A request that came before this started is not undone;
# the saver already on screen needs a remote key.
# usage: [CLIENT=<clientName>] nosaver.sh &   (stop: kill the luna-send subscription, found via /proc/*/cmdline)
luna-send -i luna://com.webos.service.tvpower/power/registerScreenSaverRequest \
  "{\"subscribe\":true,\"clientName\":\"${CLIENT:-cr120-nosaver}\"}" 2>&1 |
while read -r line; do
  # tvpower sends the timestamp as a quoted string ("timestamp": "3030189975"); the answer carries it as a number.
  ts=$(echo "$line" | sed -n 's/.*"timestamp": *\("[0-9]*"\).*/\1/p')
  [ -n "$ts" ] || continue
  luna-send -n 1 luna://com.webos.service.tvpower/power/responseScreenSaverRequest \
    "{\"clientName\":\"${CLIENT:-cr120-nosaver}\",\"ack\":false,\"timestamp\":$ts}" >> /tmp/nosaver.log 2>&1
  echo "$line" >> /tmp/nosaver.log
done
