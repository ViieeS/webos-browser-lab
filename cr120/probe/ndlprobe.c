// Does NDL DirectMedia (API 2) accept a telnet-root process that SAM did not launch?
// Calls Init(appId) and Load(H.264 1920x1080 + PCM 48 kHz stereo), prints return codes and NDL's error text.
// Struct layout from WebOS-Chromium's launcher (source/package/launcher/cnrun.c, BSD-3).
// usage on the TV: XDG_RUNTIME_DIR=/tmp/xdg WAYLAND_DISPLAY=wayland-0 ./ndlprobe <appId> [windowId]   (no windowId: exports its own VIDEO window)
// As an app (mkprobeipk.py, launched by SAM with no arguments) it writes /tmp/ndlprobe.log.
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <wayland-client.h>
#include <wayland-webos-foreign-client-protocol.h>

typedef struct {
  struct { int width, height, type, unknown1; } video;
  union {
    int type;
    struct { int type, unknown1; const char *format, *layout, *channelMode; int sampleRate; } pcm;
    char padding[32];
  } audio;
} NDL_DATA_INFO;

// An exported VIDEO window, as WebOS-Chromium's launcher makes one: NDL shows its plane through this window id.
static struct wl_compositor *comp;
static struct wl_webos_foreign *foreign;
static char window_id[128];
static void reg_global(void *d, struct wl_registry *r, uint32_t name, const char *iface, uint32_t ver) {
  if (!strcmp(iface, "wl_compositor")) comp = wl_registry_bind(r, name, &wl_compositor_interface, 1);
  else if (!strcmp(iface, "wl_webos_foreign")) foreign = wl_registry_bind(r, name, &wl_webos_foreign_interface, 1);
}
static void reg_remove(void *d, struct wl_registry *r, uint32_t name) {}
static const struct wl_registry_listener reg_l = {reg_global, reg_remove};
static void exp_id(void *d, struct wl_webos_exported *e, const char *id, uint32_t type) {
  snprintf(window_id, sizeof window_id, "%s", id);
}
static const struct wl_webos_exported_listener exp_l = {exp_id};
static struct wl_display *export_video_window(void) {
  struct wl_display *dpy = wl_display_connect(NULL);
  if (!dpy) { printf("wl_display_connect failed\n"); return NULL; }
  wl_registry_add_listener(wl_display_get_registry(dpy), &reg_l, NULL);
  wl_display_roundtrip(dpy);
  if (!comp || !foreign) { printf("no wl_compositor/wl_webos_foreign\n"); return NULL; }
  struct wl_webos_exported *ex = wl_webos_foreign_export_element(
      foreign, wl_compositor_create_surface(comp), WL_WEBOS_FOREIGN_WEBOS_EXPORTED_TYPE_VIDEO_OBJECT);
  wl_webos_exported_add_listener(ex, &exp_l, NULL);
  for (int i = 0; i < 50 && !window_id[0]; i++) wl_display_roundtrip(dpy);
  printf("exported window id: %s\n", window_id[0] ? window_id : "(none)");
  return dpy;
}

static double now(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return t.tv_sec + t.tv_nsec / 1e9;
}
static double t0;
// SAM and NDL can end the process without returning from Load: say how and when.
static void on_signal(int sig) {
  dprintf(1, "%.2f signal %d\n", now() - t0, sig);
  _exit(128 + sig);
}
static void on_exit_hook(void) { printf("%.2f exit() called\n", now() - t0); }

static void load_cb(int type, long long num, const char *str) {
  printf("callback type=%d num=%lld str=%s\n", type, num, str ? str : "-");
}

int main(int argc, char **argv) {
  // Started by SAM as app com.viiees.ndlprobe (no arguments): NDL's luna calls carry the app's identity.
  const char *app_id = argc > 1 ? argv[1] : "com.viiees.ndlprobe";
  // stdout goes to run.sh's log when started as the app
  setvbuf(stdout, NULL, _IONBF, 0);  // the TV run ends under `timeout`, which would drop buffered lines
  t0 = now();
  atexit(on_exit_hook);
  signal(SIGTERM, on_signal);
  signal(SIGINT, on_signal);
  signal(SIGHUP, on_signal);
  printf("uid=%d XDG_RUNTIME_DIR=%s WAYLAND_DISPLAY=%s\n", (int)getuid(), getenv("XDG_RUNTIME_DIR"), getenv("WAYLAND_DISPLAY"));
  void *h = dlopen("libNDL_directmedia.so.1", RTLD_NOW | RTLD_GLOBAL);
  if (!h) { printf("dlopen: %s\n", dlerror()); return 1; }
  int (*init)(const char *) = dlsym(h, "NDL_DirectMediaInit");
  int (*setwin)(const char *) = dlsym(h, "NDL_DirectMediaSetWindowId");
  int (*load)(NDL_DATA_INFO *, void (*)(int, long long, const char *)) = dlsym(h, "NDL_DirectMediaLoad");
  int (*unload)(void) = dlsym(h, "NDL_DirectMediaUnload");
  int (*quit)(void) = dlsym(h, "NDL_DirectMediaQuit");
  const char *(*err)(void) = dlsym(h, "NDL_DirectMediaGetError");
  const char *wid = argc > 2 ? argv[2] : NULL;
  if (!wid && export_video_window() && window_id[0]) wid = window_id;
  if (wid) printf("setwindow(%s) = %d\n", wid, setwin(wid));
  int r = init(app_id);
  printf("%.2f init(%s) = %d (%s)\n", now() - t0, app_id, r, r ? err() : "");
  if (r) return 1;
  NDL_DATA_INFO info;
  memset(&info, 0, sizeof info);
  info.video.type = 1;  // H.264, as cnrun passes the renderer's codec
  info.video.width = 1920;
  info.video.height = 1080;
  info.audio.pcm.type = 1;
  info.audio.pcm.format = "S16LE";
  info.audio.pcm.layout = "interleaved";
  info.audio.pcm.channelMode = "stereo";
  info.audio.pcm.sampleRate = 1;  // 48 kHz
  printf("%.2f load...\n", now() - t0);
  r = load(&info, load_cb);
  printf("%.2f load = %d (%s)\n", now() - t0, r, r ? err() : "");
  sleep(2);
  if (!r) printf("unload = %d\n", unload());
  printf("quit = %d\n", quit());
  return 0;
}
