// Main program of dev app com.viiees.cr120: starts content_shell from /media/developer/temp/cr120 as its child and
// plays its <video> streams (src and MSE) on LG's hardware decoder through NDL DirectMedia (API 2, webOS 5+).
//
// Why a launcher: LG's media stack serves only the process SAM started from the appinfo "main" ELF
// (smp::ResourceManager exit()s any other, browser/cr120/probe/ndlwin.c), and keeping NDL out of the browser means
// a resource-policy exit takes down only this process's stream, not the browser's tabs.
// Protocol and NDL calls follow WebOS-Chromium's launcher (github.com/sarahahzub/WebOS-Chromium, BSD-3,
// source/package/launcher/cnrun.c), API 2 path only. The browser side is patch 0015 plus
// extra/content/renderer/media/cn_ndl_renderer.cc (frames) and extra/ozone/wayland/foreign_window/cn_video_export.cc
// (video window id and geometry).
//
// SAM passes its launch parameters as argv[1] (JSON); a "target" URL in it is opened, otherwise about:blank.
// Logs: /tmp/cr120/launcher.log (this program), /tmp/cr120/content_shell.log (the browser).
#define _GNU_SOURCE  // accept4
#include <dlfcn.h>
#include <stdbool.h>
#include <errno.h>
#include <poll.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define DIR_ "/media/developer/temp/cr120"
#define TMP "/tmp/cr120"
#define SOCK TMP "/media.sock"
// DevTools bind address when the launch asks for it: build with -DDEVTOOLS_ADDR='"<TV LAN IP>"' to reach it
// from another machine. Never 0.0.0.0: the port has no authentication.
#ifndef DEVTOOLS_ADDR
#define DEVTOOLS_ADDR "127.0.0.1"
#endif

// Messages: header {type, payload length}, then the payload. Browser -> launcher except VSIZE.
enum { CN_OPEN = 1, CN_VIDEO = 2, CN_AUDIO = 3, CN_CLOSE = 4, CN_GEOM = 5, CN_SRC = 6, CN_WINID = 7, CN_VSIZE = 8 };
struct cn_hdr { uint32_t type, len; };
struct cn_open { uint64_t token[2]; int32_t codec, width, height, audio_rate, audio_channels; };

typedef struct {  // NDL_DIRECTMEDIA_DATA_INFO_T, API 2 (webosbrew/webos-userland)
  struct { int width, height, type, unknown1; } video;
  union {
    int type;
    struct { int type, unknown1; const char *format, *layout, *channelMode; int sampleRate; } pcm;
    char padding[32];
  } audio;
} NDL_DATA_INFO;

static void L(const char *f, ...) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  printf("%5ld.%03ld ", (long)t.tv_sec % 100000, t.tv_nsec / 1000000);
  va_list a;
  va_start(a, f);
  vprintf(f, a);
  va_end(a);
  putchar('\n');
}

// ---- NDL (dlopen: the library exists only on the TV) ----
static int (*ndl_init)(const char *), (*ndl_setwin)(const char *), (*ndl_unload)(void), (*ndl_quit)(void);
static int (*ndl_load)(NDL_DATA_INFO *, void (*)(int, long long, const char *));
static int (*ndl_vplay)(void *, unsigned, long long), (*ndl_aplay)(void *, unsigned, long long);
static const char *(*ndl_err)(void);

static int ndl_open_lib(void) {
  void *h = dlopen("libNDL_directmedia.so.1", RTLD_NOW | RTLD_GLOBAL);
  if (!h) { L("dlopen: %s", dlerror()); return 0; }
#define S(v, n) if (!(*(void **)&v = dlsym(h, n))) { L("missing %s", n); return 0; }
  S(ndl_init, "NDL_DirectMediaInit") S(ndl_setwin, "NDL_DirectMediaSetWindowId") S(ndl_load, "NDL_DirectMediaLoad")
  S(ndl_unload, "NDL_DirectMediaUnload") S(ndl_quit, "NDL_DirectMediaQuit") S(ndl_vplay, "NDL_DirectVideoPlay")
  S(ndl_aplay, "NDL_DirectAudioPlay") S(ndl_err, "NDL_DirectMediaGetError")
#undef S
  return 1;
}
static void load_cb(int type, long long num, const char *str) {
  L("ndl callback type=%d num=%lld str=%s", type, num, str ? str : "-");
}

// ---- one NDL stream at a time, owned by one renderer connection ----
static const char *app_id;
static char window_id[128];  // the browser window's exported video window (WINID)
static int winid_fd = -1;
static int ndl_ok, inited, loaded, cur_rate, cur_owner = -1;
static uint64_t cur_token[2];
static long vframes;
static struct timespec last_frame;  // when the last video frame went to NDL
static int vfails, afails;

static void stream_close(const char *why) {
  if (loaded) { L("unload (%s) = %d", why, ndl_unload()); loaded = 0; }
  if (inited) { L("quit = %d", ndl_quit()); inited = 0; }
  cur_owner = -1;
  memset(cur_token, 0, sizeof cur_token);
}

// An OPEN that arrives before the window side's WINID waits here (a fast local page opens the stream ~0.1 s first).
static struct cn_open pending_open;
static int pending_fd = -1;

static void stream_open(int fd, const struct cn_open *o) {
  stream_close("reopen");
  if (!ndl_ok) return;
  if (!window_id[0]) {
    L("open before the browser exported its video window: waiting for it");
    pending_open = *o;
    pending_fd = fd;
    return;
  }
  // Order that works on the C1 (probe/ndlwin.c): SetWindowId, Init, Load.
  int r = ndl_setwin(window_id);
  int r2 = ndl_init(app_id);
  if (r2) { L("init = %d (%s)", r2, ndl_err()); return; }
  inited = 1;
  NDL_DATA_INFO info;
  memset(&info, 0, sizeof info);
  info.video.type = o->codec;  // 1 H.264, 2 HEVC, 3 VP9, 4 AV1
  info.video.width = o->width;
  info.video.height = o->height;
  static const int rates[][2] = {{48000, 1}, {44100, 2}, {32000, 3}, {24000, 4},
                                 {16000, 5}, {12000, 6}, {8000, 7}, {22050, 8}};
  cur_rate = o->audio_rate ? o->audio_rate : 48000;
  info.audio.pcm.type = 1;
  info.audio.pcm.format = "S16LE";
  info.audio.pcm.layout = "interleaved";
  info.audio.pcm.channelMode = "stereo";
  info.audio.pcm.sampleRate = 1;
  for (unsigned i = 0; i < sizeof rates / sizeof rates[0]; i++)
    if (rates[i][0] == cur_rate) info.audio.pcm.sampleRate = rates[i][1];
  int r3 = ndl_load(&info, load_cb);
  L("open codec=%d %dx%d audio=%d: setwindow=%d init=%d load=%d (%s)", o->codec, o->width, o->height,
    o->audio_rate, r, r2, r3, r3 ? ndl_err() : "");
  if (r3) { stream_close("load failed"); return; }
  vframes = 0;
  loaded = 1;
  cur_owner = fd;
  memcpy(cur_token, o->token, sizeof cur_token);
  if (!o->audio_rate) cur_rate = 0;  // video only: we feed silence, NDL clocks by audio
  if (winid_fd >= 0) {               // the window side scales the plane's source region to the video size
    uint32_t m[4] = {CN_VSIZE, 8, (uint32_t)o->width, (uint32_t)o->height};
    if (write(winid_fd, m, sizeof m) != sizeof m) L("vsize to browser failed");
  }
}

static void on_msg(int fd, uint32_t type, unsigned char *p, uint32_t len) {
  static int16_t silence[1600 * 2];  // 33 ms of 48 kHz stereo, one video frame
  switch (type) {
  case CN_OPEN:
    if (len >= sizeof(struct cn_open)) {
      struct cn_open o;  // p sits at an odd offset after odd-sized frames: no direct uint64 loads (SIGBUS)
      memcpy(&o, p, sizeof o);
      stream_open(fd, &o);
    }
    break;
  case CN_VIDEO: case CN_AUDIO: {
    if (!loaded || fd != cur_owner || len < 8) break;
    long long pts;  // ms on the stream's NDL clock
    memcpy(&pts, p, 8);
    int r = type == CN_VIDEO ? ndl_vplay(p + 8, len - 8, pts) : ndl_aplay(p + 8, len - 8, pts);
    if (r && (type == CN_VIDEO ? vfails++ : afails++) < 10)
      L("%s play = %d (%s)", type == CN_VIDEO ? "video" : "audio", r, ndl_err());
    if (type == CN_VIDEO && !cur_rate) ndl_aplay(silence, sizeof silence, pts);
    if (type == CN_VIDEO) clock_gettime(CLOCK_MONOTONIC, &last_frame);
    if (type == CN_VIDEO && (++vframes == 1 || vframes % 1500 == 0))
      L("video frame %ld pts %lld size %u", vframes, pts, len - 8);
    break;
  }
  case CN_WINID:
    if (len > 0 && len < sizeof window_id) {
      memcpy(window_id, p, len);
      window_id[len] = 0;
      winid_fd = fd;
      L("browser exported video window %s", window_id);
      if (pending_fd >= 0) {
        int owner = pending_fd;
        pending_fd = -1;
        stream_open(owner, &pending_open);
      }
    }
    break;
  case CN_CLOSE:
    if (len >= 16 && fd == pending_fd && !memcmp(p, pending_open.token, 16)) pending_fd = -1;
    if (len >= 16 && !memcmp(p, cur_token, 16)) stream_close("close");
    break;
  case CN_GEOM:  // the window side already placed the plane; API 2 needs nothing more
  case CN_SRC:
    break;
  }
}

// ---- screensaver: webOS does not know NDL video plays, so while frames flow answer "no" to the TV ----
// tvpower asks every client registered with registerScreenSaverRequest before its idle screensaver; the request's
// timestamp is a quoted string and the answer must carry it the same way. turnOnScreenSaver skips the clients.
// Registered only while playing (as WebOS-Chromium and Kodi): paused or stopped, the TV's normal timer runs.
typedef bool (*LSFilterFunc)(void *sh, void *msg, void *ctx);
static int (*ls_register)(const char *, void **, void *), (*ls_attach)(void *, void *, void *);
static int (*ls_call)(void *, const char *, const char *, LSFilterFunc, void *, unsigned long *, void *);
static int (*ls_cancel)(void *, unsigned long, void *), (*ls_err_init)(void *);
static void (*ls_err_free)(void *);
static const char *(*ls_payload)(void *);
static void *(*g_ctx_new)(void), *(*g_loop_new)(void *, int);
static int (*g_iter)(void *, int);
static void *ls_handle, *g_ctx;
static unsigned long ss_token;
static char ss_client[160];  // "<appId>.wakelock", the name YouTube and SDL-webOS register under
static int ss_registered;

static double since(const struct timespec *t) {
  struct timespec n;
  clock_gettime(CLOCK_MONOTONIC, &n);
  return (n.tv_sec - t->tv_sec) + (n.tv_nsec - t->tv_nsec) / 1e9;
}
static int video_flowing(void) { return loaded && vframes > 0 && since(&last_frame) < 3; }

static void ss_init(void) {
  void *ls = dlopen("libluna-service2.so.3", RTLD_NOW), *g = dlopen("libglib-2.0.so.0", RTLD_NOW);
  if (!ls || !g) { L("screensaver guard off: luna/glib not found"); return; }
  *(void **)&ls_register = dlsym(ls, "LSRegister");
  *(void **)&ls_attach = dlsym(ls, "LSGmainAttach");
  *(void **)&ls_call = dlsym(ls, "LSCall");
  *(void **)&ls_cancel = dlsym(ls, "LSCallCancel");
  *(void **)&ls_err_init = dlsym(ls, "LSErrorInit");
  *(void **)&ls_err_free = dlsym(ls, "LSErrorFree");
  *(void **)&ls_payload = dlsym(ls, "LSMessageGetPayload");
  *(void **)&g_ctx_new = dlsym(g, "g_main_context_new");
  *(void **)&g_loop_new = dlsym(g, "g_main_loop_new");
  *(void **)&g_iter = dlsym(g, "g_main_context_iteration");
  if (!ls_register || !ls_attach || !ls_call || !ls_cancel || !ls_err_init || !ls_payload || !g_ctx_new ||
      !g_loop_new || !g_iter) { L("screensaver guard off: luna symbols missing"); return; }
  char err[64] = {0};  // LSError, opaque here; 64 bytes covers it
  ls_err_init(err);
  void *h = NULL;
  if (!ls_register(NULL, &h, err) || !h) { L("screensaver guard off: LSRegister refused"); return; }
  g_ctx = g_ctx_new();
  if (!ls_attach(h, g_loop_new(g_ctx, 0), err)) { L("screensaver guard off: LSGmainAttach failed"); return; }
  ls_handle = h;
  snprintf(ss_client, sizeof ss_client, "%s.wakelock", app_id);
  L("screensaver guard ready (%s)", ss_client);
}

static bool ss_on_reply(void *sh, void *msg, void *ctx) {
  const char *p = ls_payload(msg);
  L("screensaver luna message %.160s", p ? p : "(null)");
  const char *t = p ? strstr(p, "\"timestamp\"") : NULL;
  if (!t || !(t = strchr(t + 11, '"'))) return true;  // the subscribe reply itself
  const char *end = strchr(t + 1, '"');
  if (!end || end - t > 40) return true;
  char resp[400], err[64] = {0};
  snprintf(resp, sizeof resp, "{\"clientName\":\"%s\",\"ack\":%s,\"timestamp\":%.*s}", ss_client,
           video_flowing() ? "false" : "true", (int)(end - t + 1), t);
  ls_err_init(err);
  ls_call(ls_handle, "luna://com.webos.service.tvpower/power/responseScreenSaverRequest", resp, NULL, NULL, NULL, err);
  L("screensaver request answered %s", video_flowing() ? "no (video playing)" : "yes");
  return true;
}

// Once per main-loop pass: dispatch luna replies, register while video flows, cancel 3 s after it stops.
static void ss_tick(void) {
  if (!ls_handle) return;
  for (int n = 0; n < 16 && g_iter(g_ctx, 0); n++) {}
  char err[64] = {0};
  ls_err_init(err);
  if (video_flowing() && !ss_registered) {
    char reg[200];
    snprintf(reg, sizeof reg, "{\"subscribe\":true,\"clientName\":\"%s\"}", ss_client);
    if (ls_call(ls_handle, "luna://com.webos.service.tvpower/power/registerScreenSaverRequest", reg, ss_on_reply,
                NULL, &ss_token, err)) {
      ss_registered = 1;
      L("screensaver held off (video playing)");
    }
  } else if (!video_flowing() && ss_registered) {
    ls_cancel(ls_handle, ss_token, err);
    ss_registered = 0;
    L("screensaver back to the TV's timer");
  }
}

// ---- clients: each renderer stream and the window side connect separately ----
#define MAXC 16
static struct client { int fd; unsigned char *buf; size_t n, cap; } cl[MAXC];

static void client_drop(struct client *c) {
  if (c->fd == cur_owner) stream_close("client gone");
  if (c->fd == pending_fd) pending_fd = -1;
  if (c->fd == winid_fd) { winid_fd = -1; window_id[0] = 0; }
  close(c->fd);
  free(c->buf);
  memset(c, 0, sizeof *c);
  c->fd = -1;
}

static void client_read(struct client *c) {
  for (;;) {
    if (c->cap - c->n < 65536) {
      size_t nc = c->cap ? c->cap * 2 : 262144;
      unsigned char *nb = realloc(c->buf, nc);
      if (!nb) { client_drop(c); return; }
      c->buf = nb;
      c->cap = nc;
    }
    ssize_t r = read(c->fd, c->buf + c->n, c->cap - c->n);
    if (r == 0) { client_drop(c); return; }
    if (r < 0) {
      if (errno == EINTR) continue;
      if (errno != EAGAIN) client_drop(c);
      break;
    }
    c->n += r;
    size_t off = 0;
    while (c->n - off >= sizeof(struct cn_hdr)) {
      struct cn_hdr h;
      memcpy(&h, c->buf + off, sizeof h);
      if (h.len > 64 << 20) { L("bad message len %u", h.len); client_drop(c); return; }
      if (c->n - off - sizeof h < h.len) break;
      on_msg(c->fd, h.type, c->buf + off + sizeof h, h.len);
      off += sizeof h + h.len;
    }
    memmove(c->buf, c->buf + off, c->n - off);
    c->n -= off;
  }
}

// ---- process ----
static volatile sig_atomic_t got_term, got_chld;
static void on_sig(int sig) {
  if (sig == SIGCHLD) got_chld = 1;
  else got_term = sig;
}

// The value of "target" in SAM's JSON parameters if it is an http(s) or about: URL, else NULL. Anything else
// could reach content_shell's argv as a switch (--renderer-cmd-prefix runs a command), so it is dropped.
static char *target_url(const char *json) {
  const char *k = json ? strstr(json, "\"target\"") : NULL;
  if (!k || !(k = strchr(k + 8, '"'))) return NULL;
  const char *end = strchr(k + 1, '"');
  if (!end) return NULL;
  char *url = strndup(k + 1, end - k - 1);
  if (url && (!strncmp(url, "http://", 7) || !strncmp(url, "https://", 8) || !strncmp(url, "about:", 6)))
    return url;
  L("target %.80s refused: only http, https and about URLs", url ? url : "?");
  free(url);
  return NULL;
}

// True when SAM's parameters ask for DevTools ("devtools":true). Off by default: the port has no authentication,
// and anyone on the LAN would control the browser.
static int devtools_wanted(const char *json) {
  const char *k = json ? strstr(json, "\"devtools\"") : NULL;
  if (!k || !(k = strchr(k + 10, ':'))) return 0;
  while (*++k == ' ') {}
  return !strncmp(k, "true", 4);
}

static int listen_socket(void) {
  int s = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
  struct sockaddr_un a = {.sun_family = AF_UNIX};
  snprintf(a.sun_path, sizeof a.sun_path, "%s", SOCK);
  unlink(SOCK);
  if (s < 0 || bind(s, (struct sockaddr *)&a, sizeof a) || listen(s, 8)) {
    L("media socket: %s", strerror(errno));
    if (s >= 0) close(s);
    return -1;
  }
  return s;
}

int main(int argc, char **argv) {
  mkdir(TMP, 0777);
  if (!freopen(TMP "/launcher.log", "w", stdout)) return 1;
  setvbuf(stdout, NULL, _IONBF, 0);
  app_id = getenv("APPID") ? getenv("APPID") : "com.viiees.cr120";
  char *url = target_url(argc > 1 ? argv[1] : NULL);
  int devtools = devtools_wanted(argc > 1 ? argv[1] : NULL);
  L("cr120run pid %d uid %d appid %s url %s devtools %s", (int)getpid(), (int)getuid(), app_id,
    url ? url : "about:blank", devtools ? "on (" DEVTOOLS_ADDR ":9224)" : "off");
  ndl_ok = ndl_open_lib();
  if (ndl_ok) ss_init();
  int ls = ndl_ok ? listen_socket() : -1;
  if (ls >= 0) setenv("CN_MEDIA_SOCK", SOCK, 1);  // turns on the browser's NDL path (renderer, viz, ozone)
  L("hardware video %s", ls >= 0 ? "on" : "off");
  setenv("XDG_RUNTIME_DIR", "/tmp/xdg", 1);
  setenv("WAYLAND_DISPLAY", "wayland-0", 1);
  setenv("FONTCONFIG_FILE", DIR_ "/fonts.conf", 1);
  setenv("LD_LIBRARY_PATH", DIR_ "/lib", 1);
  struct sigaction sa;
  memset(&sa, 0, sizeof sa);
  sa.sa_handler = on_sig;
  sigaction(SIGCHLD, &sa, NULL);
  sigaction(SIGTERM, &sa, NULL);
  sigaction(SIGINT, &sa, NULL);
  sigaction(SIGHUP, &sa, NULL);
  pid_t child = fork();
  if (child == 0) {
    setpgid(0, 0);  // its own group: on close the launcher can end every browser process at once
    if (ls >= 0) close(ls);
    if (!freopen(TMP "/content_shell.log", "w", stdout)) _exit(126);
    dup2(fileno(stdout), 2);
    if (chdir(DIR_)) _exit(126);
    // Flags as run_tv.sh (see the reasons there).
    const char *av[24];
    int n = 0;
    av[n++] = "content_shell";
    av[n++] = "--no-sandbox";
    av[n++] = "--ozone-platform=wayland_external";
    av[n++] = "--user-data-dir=" TMP "/profile";
    av[n++] = "--enable-logging=stderr";
    av[n++] = "--v=0";
    av[n++] = "--content-shell-host-window-size=1920x1080";  // default 800x600, which LSM stretches to the panel
    av[n++] = "--disable-gl-extensions=GL_EXT_robustness GL_KHR_robustness";
    av[n++] = "--disable-gpu-rasterization";
    // With NDL, <video src> also takes Chromium's pipeline (and so NDL) instead of the neva player, whose
    // uMediaServer path spawns luna-send, which the app's jail does not allow.
    if (ls >= 0) av[n++] = "--disable-web-media-player-neva";
    if (devtools) {  // only on the TV's LAN IP, only when the launch asked for it
      av[n++] = "--remote-debugging-address=" DEVTOOLS_ADDR;
      av[n++] = "--remote-debugging-port=9224";
    }
    av[n++] = "--";  // base::CommandLine stops reading switches here: the URL can never become one
    av[n++] = url ? url : "about:blank";
    av[n] = NULL;
    execv(DIR_ "/content_shell", (char *const *)av);
    _exit(127);
  }
  L("content_shell pid %d", (int)child);
  for (int i = 0; i < MAXC; i++) cl[i].fd = -1;
  int status = 0;
  struct timespec term_at = {0};
  for (;;) {
    // SAM kills an app that does not end soon after SIGTERM, which orphaned a busy content_shell (YouTube):
    // forward the signal, and 2 s later kill the browser's whole process group.
    if (got_term) { kill(child, got_term); got_term = 0; clock_gettime(CLOCK_MONOTONIC, &term_at); }
    if (term_at.tv_sec && since(&term_at) > 2) { L("content_shell still running 2 s after the close: killed"); kill(-child, SIGKILL); term_at.tv_sec = 0; }
    if (got_chld) {
      got_chld = 0;
      if (waitpid(child, &status, WNOHANG) == child) break;
    }
    struct pollfd pf[MAXC + 1];
    int n = 0, cmap[MAXC + 1];
    if (ls >= 0) { pf[n].fd = ls; pf[n].events = POLLIN; cmap[n++] = -1; }
    for (int i = 0; i < MAXC; i++)
      if (cl[i].fd >= 0) { pf[n].fd = cl[i].fd; pf[n].events = POLLIN; cmap[n++] = i; }
    int pr = poll(pf, n, 250);
    ss_tick();
    if (pr < 0) continue;
    for (int k = 0; k < n; k++) {
      if (!pf[k].revents) continue;
      if (cmap[k] >= 0) { client_read(&cl[cmap[k]]); continue; }
      int c = accept4(ls, NULL, NULL, SOCK_CLOEXEC | SOCK_NONBLOCK);
      if (c < 0) continue;
      int slot = -1;
      for (int i = 0; i < MAXC; i++)
        if (cl[i].fd < 0) { slot = i; break; }
      if (slot < 0) { close(c); continue; }
      cl[slot].fd = c;
    }
  }
  stream_close("exit");
  if (ls >= 0) unlink(SOCK);
  L("content_shell exited, status 0x%x", status);
  return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}
