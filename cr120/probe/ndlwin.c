// Plays an Annex-B H.264 file through NDL DirectMedia (API 2) the way WebOS-Chromium's browser does it
// (source/patches/0025, package/launcher/cnrun.c): a fullscreen webOS card of this app, kept transparent, exports
// the video window from its own surface, places it full screen with mute=off, and only then NDL SetWindowId, Init,
// Load. Frames are split at access unit delimiters (encode with x264 aud=1) and fed at 30 fps; audio is silence.
// Run as a SAM-launched app (mkprobeipk.py): NDL ends the process on Load otherwise.
// usage: ndlwin [file.h264, default clip.h264] [seconds]   (writes progress to stdout)
#include <EGL/egl.h>
#include <GLES2/gl2.h>
#include <dlfcn.h>
#include <execinfo.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <wayland-client.h>
#include <wayland-egl.h>
#include <wayland-webos-foreign-client-protocol.h>
#include <wayland-webos-shell-client-protocol.h>

typedef struct {
  struct { int width, height, type, unknown1; } video;
  union {
    int type;
    struct { int type, unknown1; const char *format, *layout, *channelMode; int sampleRate; } pcm;
    char padding[32];
  } audio;
} NDL_DATA_INFO;

static struct wl_compositor *comp;
static struct wl_shell *shell;
static struct wl_webos_shell *webos_shell;
static struct wl_webos_foreign *foreign;
static char window_id[128];
static double t0;

static double now(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return t.tv_sec + t.tv_nsec / 1e9;
}
// NDL_DirectMediaLoad has ended the process with exit(): print who called it.
static void on_exit_hook(void) {
  printf("%.2f exit() called\n", now() - t0);
  void *pc[32];
  backtrace_symbols_fd(pc, backtrace(pc, 32), 1);
}

static void reg_global(void *d, struct wl_registry *r, uint32_t name, const char *iface, uint32_t ver) {
  if (!strcmp(iface, "wl_compositor")) comp = wl_registry_bind(r, name, &wl_compositor_interface, 3);
  else if (!strcmp(iface, "wl_shell")) shell = wl_registry_bind(r, name, &wl_shell_interface, 1);
  else if (!strcmp(iface, "wl_webos_shell")) webos_shell = wl_registry_bind(r, name, &wl_webos_shell_interface, 1);
  else if (!strcmp(iface, "wl_webos_foreign")) foreign = wl_registry_bind(r, name, &wl_webos_foreign_interface, 1);
}
static void reg_remove(void *d, struct wl_registry *r, uint32_t name) {}
static const struct wl_registry_listener reg_l = {reg_global, reg_remove};
static void ping(void *d, struct wl_shell_surface *s, uint32_t serial) { wl_shell_surface_pong(s, serial); }
static void configure(void *d, struct wl_shell_surface *s, uint32_t e, int32_t w, int32_t h) {}
static void popup_done(void *d, struct wl_shell_surface *s) {}
static const struct wl_shell_surface_listener ss_l = {ping, configure, popup_done};
static void ws_state(void *d, struct wl_webos_shell_surface *s, uint32_t st) { printf("%.2f window state %u\n", now() - t0, st); }
static void ws_pos(void *d, struct wl_webos_shell_surface *s, int32_t x, int32_t y) {}
static void ws_close(void *d, struct wl_webos_shell_surface *s) { printf("close requested\n"); exit(0); }
static void ws_expose(void *d, struct wl_webos_shell_surface *s, struct wl_array *r) {}
static void ws_state_about(void *d, struct wl_webos_shell_surface *s, uint32_t st) {}
static void ws_addon(void *d, struct wl_webos_shell_surface *s, uint32_t st) {}
static const struct wl_webos_shell_surface_listener ws_l = {ws_state, ws_pos, ws_close, ws_expose, ws_state_about, ws_addon};
static void exp_id(void *d, struct wl_webos_exported *e, const char *id, uint32_t type) {
  snprintf(window_id, sizeof window_id, "%s", id);
}
static const struct wl_webos_exported_listener exp_l = {exp_id};

static void load_cb(int type, long long num, const char *str) {
  printf("%.2f ndl callback type=%d num=%lld str=%s\n", now() - t0, type, num, str ? str : "-");
}

// Next access unit in buf[*pos..n): from one AUD start code to the next.
static const unsigned char *next_au(const unsigned char *buf, size_t n, size_t *pos, size_t *len) {
  static const unsigned char aud[] = {0, 0, 0, 1, 9};
  if (*pos >= n) return NULL;
  size_t start = *pos, i = start + sizeof aud;
  while (i + sizeof aud <= n && memcmp(buf + i, aud, sizeof aud)) i++;
  if (i + sizeof aud > n) i = n;
  *len = i - start;
  *pos = i;
  return buf + start;
}

int main(int argc, char **argv) {
  // Launched by SAM: stdout is nowhere, and argv[1] is SAM's JSON parameters, not a file.
  int from_sam = getenv("APPID") != NULL;
  if (from_sam && !freopen("/tmp/ndlwin.log", "w", stdout)) return 1;
  if (from_sam) dup2(fileno(stdout), 2);
  setvbuf(stdout, NULL, _IONBF, 0);
  t0 = now();
  atexit(on_exit_hook);
  const char *path = argc > 1 && !from_sam ? argv[1] : "clip.h264";
  int seconds = argc > 2 && !from_sam ? atoi(argv[2]) : 10;
  const char *app_id = getenv("APPID") ? getenv("APPID") : "com.viiees.ndlprobe";
  FILE *f = fopen(path, "rb");
  if (!f) { perror(path); return 1; }
  fseek(f, 0, SEEK_END);
  size_t n = ftell(f);
  fseek(f, 0, SEEK_SET);
  unsigned char *es = malloc(n);
  if (fread(es, 1, n, f) != n) { printf("short read\n"); return 1; }
  fclose(f);

  struct wl_display *dpy = wl_display_connect(NULL);
  if (!dpy) { printf("wl_display_connect failed\n"); return 1; }
  wl_registry_add_listener(wl_display_get_registry(dpy), &reg_l, NULL);
  wl_display_roundtrip(dpy);
  if (!comp || !shell || !webos_shell || !foreign) { printf("missing wayland globals\n"); return 1; }
  struct wl_surface *surf = wl_compositor_create_surface(comp);
  struct wl_shell_surface *ss = wl_shell_get_shell_surface(shell, surf);
  wl_shell_surface_add_listener(ss, &ss_l, NULL);
  wl_shell_surface_set_toplevel(ss);
  struct wl_webos_shell_surface *ws = wl_webos_shell_get_shell_surface(webos_shell, surf);
  wl_webos_shell_surface_add_listener(ws, &ws_l, NULL);
  wl_webos_shell_surface_set_property(ws, "appId", app_id);
  wl_webos_shell_surface_set_property(ws, "_WEBOS_WINDOW_TYPE", "_WEBOS_WINDOW_TYPE_CARD");
  wl_webos_shell_surface_set_state(ws, WL_WEBOS_SHELL_SURFACE_STATE_FULLSCREEN);

  struct wl_egl_window *win = wl_egl_window_create(surf, 1920, 1080);
  EGLDisplay ed = eglGetDisplay((EGLNativeDisplayType)dpy);
  EGLint maj, min;
  if (!eglInitialize(ed, &maj, &min)) { printf("eglInitialize failed\n"); return 1; }
  EGLint ca[] = {EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8,
                 EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_NONE};
  EGLConfig cfg;
  EGLint nc;
  eglChooseConfig(ed, ca, &cfg, 1, &nc);
  EGLint cx[] = {EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE};
  EGLContext ctx = eglCreateContext(ed, cfg, EGL_NO_CONTEXT, cx);
  EGLSurface egl_surf = eglCreateWindowSurface(ed, cfg, (EGLNativeWindowType)win, NULL);
  eglMakeCurrent(ed, egl_surf, egl_surf, ctx);
  glClearColor(0, 0, 0, 0);  // the video plane is below the window: a transparent window shows it
  glClear(GL_COLOR_BUFFER_BIT);
  eglSwapBuffers(ed, egl_surf);
  wl_display_roundtrip(dpy);

  struct wl_webos_exported *ex = wl_webos_foreign_export_element(foreign, surf, WL_WEBOS_FOREIGN_WEBOS_EXPORTED_TYPE_VIDEO_OBJECT);
  wl_webos_exported_add_listener(ex, &exp_l, NULL);
  for (int i = 0; i < 50 && !window_id[0]; i++) wl_display_roundtrip(dpy);
  printf("%.2f exported window id: %s\n", now() - t0, window_id[0] ? window_id : "(none)");
  if (!window_id[0]) return 1;
  struct wl_region *src = wl_compositor_create_region(comp);
  wl_region_add(src, 0, 0, 1920, 1080);
  struct wl_region *dst = wl_compositor_create_region(comp);
  wl_region_add(dst, 0, 0, 1920, 1080);
  wl_webos_exported_set_exported_window(ex, src, dst);
  wl_webos_exported_set_property(ex, "mute", "off");
  wl_display_roundtrip(dpy);

  void *h = dlopen("libNDL_directmedia.so.1", RTLD_NOW | RTLD_GLOBAL);
  if (!h) { printf("dlopen: %s\n", dlerror()); return 1; }
  int (*init)(const char *) = dlsym(h, "NDL_DirectMediaInit");
  int (*setwin)(const char *) = dlsym(h, "NDL_DirectMediaSetWindowId");
  int (*load)(NDL_DATA_INFO *, void (*)(int, long long, const char *)) = dlsym(h, "NDL_DirectMediaLoad");
  int (*vplay)(void *, unsigned, long long) = dlsym(h, "NDL_DirectVideoPlay");
  int (*aplay)(void *, unsigned, long long) = dlsym(h, "NDL_DirectAudioPlay");
  int (*unload)(void) = dlsym(h, "NDL_DirectMediaUnload");
  int (*quit)(void) = dlsym(h, "NDL_DirectMediaQuit");
  const char *(*err)(void) = dlsym(h, "NDL_DirectMediaGetError");
  printf("%.2f setwindow = %d\n", now() - t0, setwin(window_id));
  int r = init(app_id);
  printf("%.2f init(%s) = %d (%s)\n", now() - t0, app_id, r, r ? err() : "");
  if (r) return 1;
  NDL_DATA_INFO info;
  memset(&info, 0, sizeof info);
  info.video.type = 1;  // H.264
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
  if (r) return 1;

  static short silence[1600 * 2];  // 1600 frames = 33 ms at 48 kHz, one video frame
  size_t pos = 0, len;
  long frames = 0, vfail = 0;
  double start = now();
  while (now() - start < seconds) {
    const unsigned char *au = next_au(es, n, &pos, &len);
    if (!au) { pos = 0; continue; }
    long long pts = frames * 1000 / 30;
    if (vplay((void *)au, len, pts) && vfail++ < 5) printf("video play = fail (%s)\n", err());
    aplay(silence, sizeof silence, pts);
    frames++;
    double due = start + frames / 30.0;
    while (now() < due) {
      glClear(GL_COLOR_BUFFER_BIT);
      eglSwapBuffers(ed, egl_surf);
      wl_display_dispatch_pending(dpy);
      if (now() < due) usleep(2000);
    }
  }
  printf("%.2f fed %ld frames, %ld video failures\n", now() - t0, frames, vfail);
  printf("unload = %d, quit = %d\n", unload(), quit());
  return 0;
}
