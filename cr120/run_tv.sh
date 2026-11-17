#!/bin/sh
# Starts chromium120 content_shell on the C1 as root from a telnet shell, detached.
# The window shows because src/ozone/wayland creates a wl_webos_shell surface (no SAM needed).
# usage: run_tv.sh <url> [extra content_shell flags...]   (stop: run_tv.sh stop)
# DevTools listens on the TV's LAN IP only, port 9224.
# Mali reports a GL context reset ~1-4 s into every GPU process unless the robustness extensions
# are hidden (validating decoder, egl-gles2).
# GPU raster draws images as solid green boxes on Mali: tiles are rastered on the CPU, composited on the GPU.
D=/media/developer/temp/cr120
# busybox ps/pkill in the telnet shell do not see processes started by an earlier session.
grep -l content_shell /proc/[0-9]*/comm 2>/dev/null | cut -d/ -f3 | xargs -r kill -9
# The media client loads pipelines through short-lived luna-send calls, so uMediaServer does not
# drop them when content_shell dies: unload every pipeline of its appId (com.webos.app.1).
luna-send -n 1 luna://com.webos.media/getActivePipelines '{}' | tr '{' '\n' \
  | grep '"appId":"com.webos.app.1"' | sed -n 's/.*"id":"\([^"]*\)".*/\1/p' \
  | xargs -r -I{} luna-send -n 1 luna://com.webos.media/unload '{"mediaId":"{}"}' > /dev/null
[ "$1" = stop ] && exit 0
URL=$1; shift
export XDG_RUNTIME_DIR=/tmp/xdg WAYLAND_DISPLAY=wayland-0
export FONTCONFIG_FILE=$D/fonts.conf
export LD_LIBRARY_PATH=$D/lib
mkdir -p /tmp/cr120-profile
cd $D
setsid $D/content_shell --no-sandbox --ozone-platform=wayland_external \
  --user-data-dir=/tmp/cr120-profile --remote-debugging-address=${DEVTOOLS_ADDR:-127.0.0.1} \
  --remote-debugging-port=9224 --enable-logging=stderr --v=0 \
  "--disable-gl-extensions=GL_EXT_robustness GL_KHR_robustness" \
  --disable-gpu-rasterization \
  "$@" "$URL" > /tmp/cr120.log 2>&1 < /dev/null &
echo started pid $!
