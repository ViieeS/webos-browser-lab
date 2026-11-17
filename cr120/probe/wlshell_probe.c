// Gate test for Chromium's Intel ozone backend: does the C1 compositor show a
// plain wl_shell surface (mode "plain") or one that also carries a
// wl_webos_shell surface (mode "webos") when the client is not SAM-launched?
// Usage: wlshell_probe plain|webos [seconds]
#include <EGL/egl.h>
#include <GLES2/gl2.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <wayland-client.h>
#include <wayland-egl.h>
#include <wayland-webos-shell-client-protocol.h>

static struct wl_compositor *compositor;
static struct wl_shell *shell;
static struct wl_webos_shell *webos_shell;

static void global_add(void *d, struct wl_registry *r, uint32_t name,
                       const char *iface, uint32_t ver) {
  if (!strcmp(iface, "wl_compositor"))
    compositor = wl_registry_bind(r, name, &wl_compositor_interface, 3);
  else if (!strcmp(iface, "wl_shell"))
    shell = wl_registry_bind(r, name, &wl_shell_interface, 1);
  else if (!strcmp(iface, "wl_webos_shell"))
    webos_shell = wl_registry_bind(r, name, &wl_webos_shell_interface, 1);
}
static void global_remove(void *d, struct wl_registry *r, uint32_t n) {}
static const struct wl_registry_listener reg_listener = {global_add,
                                                         global_remove};

static void ping(void *d, struct wl_shell_surface *s, uint32_t serial) {
  wl_shell_surface_pong(s, serial);
}
static void configure(void *d, struct wl_shell_surface *s, uint32_t e,
                      int32_t w, int32_t h) {
  fprintf(stderr, "configure %dx%d\n", w, h);
}
static void popup_done(void *d, struct wl_shell_surface *s) {}
static const struct wl_shell_surface_listener ss_listener = {ping, configure,
                                                             popup_done};

static void ws_state(void *d, struct wl_webos_shell_surface *s, uint32_t st) {
  fprintf(stderr, "webos state %u\n", st);
}
static void ws_pos(void *d, struct wl_webos_shell_surface *s, int32_t x,
                   int32_t y) {}
static void ws_close(void *d, struct wl_webos_shell_surface *s) {
  fprintf(stderr, "webos close\n");
  exit(0);
}
static void ws_expose(void *d, struct wl_webos_shell_surface *s,
                      struct wl_array *r) {
  fprintf(stderr, "webos exposed\n");
}
static void ws_state_about(void *d, struct wl_webos_shell_surface *s,
                           uint32_t st) {}
static void ws_addon(void *d, struct wl_webos_shell_surface *s, uint32_t st) {}
static const struct wl_webos_shell_surface_listener ws_listener = {
    ws_state, ws_pos, ws_close, ws_expose, ws_state_about, ws_addon};

int main(int argc, char **argv) {
  int webos = argc > 1 && !strcmp(argv[1], "webos");
  int seconds = argc > 2 ? atoi(argv[2]) : 8;
  struct wl_display *dpy = wl_display_connect(NULL);
  if (!dpy) { fprintf(stderr, "no display\n"); return 1; }
  struct wl_registry *reg = wl_display_get_registry(dpy);
  wl_registry_add_listener(reg, &reg_listener, NULL);
  wl_display_roundtrip(dpy);
  fprintf(stderr, "compositor=%p shell=%p webos_shell=%p\n", compositor, shell,
          webos_shell);
  struct wl_surface *surf = wl_compositor_create_surface(compositor);
  struct wl_shell_surface *ss = wl_shell_get_shell_surface(shell, surf);
  wl_shell_surface_add_listener(ss, &ss_listener, NULL);
  wl_shell_surface_set_toplevel(ss);
  wl_shell_surface_set_title(ss, "cr120probe");
  if (webos) {
    struct wl_webos_shell_surface *ws =
        wl_webos_shell_get_shell_surface(webos_shell, surf);
    wl_webos_shell_surface_add_listener(ws, &ws_listener, NULL);
    wl_webos_shell_surface_set_property(ws, "appId",
                                        getenv("APPID") ? getenv("APPID")
                                                        : "com.viiees.cr120probe");
    wl_webos_shell_surface_set_property(ws, "_WEBOS_WINDOW_TYPE",
                                        "_WEBOS_WINDOW_TYPE_CARD");
    wl_webos_shell_surface_set_state(ws, WL_WEBOS_SHELL_SURFACE_STATE_FULLSCREEN);
  }
  struct wl_egl_window *win = wl_egl_window_create(surf, 1920, 1080);
  EGLDisplay ed = eglGetDisplay((EGLNativeDisplayType)dpy);
  EGLint maj, min;
  if (!eglInitialize(ed, &maj, &min)) { fprintf(stderr, "eglInitialize\n"); return 1; }
  EGLint ca[] = {EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8,
                 EGL_ALPHA_SIZE, 8, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
                 EGL_NONE};
  EGLConfig cfg; EGLint n;
  eglChooseConfig(ed, ca, &cfg, 1, &n);
  EGLint cx[] = {EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE};
  EGLContext ctx = eglCreateContext(ed, cfg, EGL_NO_CONTEXT, cx);
  EGLSurface es = eglCreateWindowSurface(ed, cfg, (EGLNativeWindowType)win, NULL);
  if (es == EGL_NO_SURFACE) { fprintf(stderr, "surface err %x\n", eglGetError()); return 1; }
  eglMakeCurrent(ed, es, es, ctx);
  time_t end = time(NULL) + seconds;
  int frames = 0;
  while (time(NULL) < end) {
    float t = (frames % 120) / 120.0f;
    glClearColor(webos ? 0.0f : 1.0f, t, webos ? 1.0f : 0.0f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT);
    eglSwapBuffers(ed, es);
    wl_display_dispatch_pending(dpy);
    frames++;
  }
  fprintf(stderr, "frames=%d in %ds\n", frames, seconds);
  return 0;
}
