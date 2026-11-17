#!/bin/sh
# Starts the aarch64 MiniBrowser headless on the TV (WPEPlatform headless display, Mesa llvmpipe for
# GL), with Web Inspector on the TV's LAN address so browser/bench/timeline.py and speedo64.py can
# drive it. No window: this measures the 64-bit engine (JS, styles, layout, paint on the CPU).
# usage: run64.sh <url> [inspector port, default 9223]   (detaches; log in /tmp/wpe64.log)
D=/media/developer/temp/wpe64
export WEBKIT_EXEC_PATH=$D/libexec
export GST_PLUGIN_SYSTEM_PATH=$D/lib/gstreamer-1.0 GST_PLUGIN_SYSTEM_PATH_1_0=$D/lib/gstreamer-1.0
export GST_REGISTRY=/tmp/wpe64-gst.bin GST_REGISTRY_FORK=no
unset GST_PLUGIN_PATH GST_PLUGIN_PATH_1_0 GST_PLUGIN_SCANNER GIO_EXTRA_MODULES
export GIO_MODULE_DIR=$D/lib/gio/modules
export SSL_CERT_FILE=$D/etc/ssl/certs/ca-certificates.crt
export FONTCONFIG_FILE=$D/etc/fonts/fonts.conf
export XDG_CACHE_HOME=/tmp/wpe64-cache XDG_DATA_HOME=/tmp/wpe64-data
export WEBKIT_DISABLE_PSON=1
# The 32-bit host's UA (desktop Safari): sites pick their bundles by it (patch 0013 reads this).
export MINIBROWSER_USER_AGENT='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15'
export EGL_PLATFORM=surfaceless LIBGL_ALWAYS_SOFTWARE=1
export WEBKIT_INSPECTOR_HTTP_SERVER=${DEVTOOLS_ADDR:-127.0.0.1}:${2:-9223} WEBKIT_INSPECTOR_RESOURCES_PATH=$D
mkdir -p /tmp/wpe64-cache /tmp/wpe64-data
nohup $D/bin/MiniBrowser --headless --size=1280x720 "$1" > /tmp/wpe64.log 2>&1 &
echo started $!
