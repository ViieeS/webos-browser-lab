// TV browser host: one SDL window on the webOS compositor, WPE WebKit drawing into it.
//
// The LG compositor offers wl_shell + wl_webos_shell only (no xdg-shell, no dmabuf), so WPE's own
// Wayland platforms cannot show a window. Instead wpebackend-fdo runs a private Wayland server in
// this process (the vendor EGL has EGL_WL_bind_wayland_display), WebKit's web process renders into
// it, and every finished frame arrives here as an EGLImage that we draw as a texture.
//
// usage: browser [url]
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>
#include <SDL2/SDL.h>
#include <glib.h>
#include <stdio.h>
#include <string.h>
#include <stdbool.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <unistd.h>
#include <wpe/fdo-egl.h>
#include <wpe/fdo.h>
#include <wpe/webkit.h>

#define WIDTH 1920
#define HEIGHT 1080
#define SCANCODE_WEBOS_BACK 482

static struct {
    SDL_Window *window;
    struct wpe_view_backend_exportable_fdo *exportable;
    struct wpe_view_backend *backend;
    WebKitWebView *view;
    struct wpe_fdo_egl_exported_image *pending;  // newest frame from WebKit, not drawn yet
    struct wpe_fdo_egl_exported_image *shown;    // frame on screen; released once replaced
    GLuint texture, program;
    PFNGLEGLIMAGETARGETTEXTURE2DOESPROC image_target_texture;
    WebKitInputMethodContext *input;
    bool quit;
    bool trace_frames;   // perf runs (launch param autoscroll) log PRESENT lines
    bool wheel_probe;    // autoscroll=wheel: the host scrolls like a user, see wheel_tick
    unsigned wheel_delay_ms;   // launch param wheeldelay: how long after load the wheel starts
    // Size WebKit lays out and rasterizes at; the GL quad stretches it over the 1920x1080 window.
    // 1280x720 by default: the Mali-G51 rasterizes 2.25x fewer pixels (wheel scroll 24 -> 34 fps)
    // and desktop layouts read from the couch. Launch param view=1920x1080 restores native size.
    int view_w, view_h;
} host = {.view_w = 1280, .view_h = 720};

static uint32_t now_ms(void) { return SDL_GetTicks(); }
static int to_view_x(int x) { return x * host.view_w / WIDTH; }
static int to_view_y(int y) { return y * host.view_h / HEIGHT; }

static void on_frame(void *data, struct wpe_fdo_egl_exported_image *image)
{
    if (host.pending)                        // WebKit outran the display: drop the older frame
        wpe_view_backend_exportable_fdo_egl_dispatch_release_exported_image(host.exportable, host.pending);
    host.pending = image;
}

static GLuint compile(GLenum type, const char *src)
{
    GLuint s = glCreateShader(type);
    glShaderSource(s, 1, &src, NULL);
    glCompileShader(s);
    GLint ok;
    glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char log[512];
        glGetShaderInfoLog(s, sizeof log, NULL, log);
        fprintf(stderr, "shader: %s\n", log);
    }
    return s;
}

static void gl_setup(void)
{
    static const char *vs =
        "attribute vec2 pos; varying vec2 uv;\n"
        "void main() { uv = vec2(pos.x * 0.5 + 0.5, 0.5 - pos.y * 0.5); gl_Position = vec4(pos, 0.0, 1.0); }\n";
    static const char *fs =
        "precision mediump float; varying vec2 uv; uniform sampler2D tex;\n"
        "void main() { gl_FragColor = texture2D(tex, uv); }\n";
    host.program = glCreateProgram();
    glAttachShader(host.program, compile(GL_VERTEX_SHADER, vs));
    glAttachShader(host.program, compile(GL_FRAGMENT_SHADER, fs));
    glBindAttribLocation(host.program, 0, "pos");
    glLinkProgram(host.program);
    glUseProgram(host.program);
    static const GLfloat quad[] = {-1, -1, 1, -1, -1, 1, 1, 1};
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, quad);
    glEnableVertexAttribArray(0);
    glGenTextures(1, &host.texture);
    glBindTexture(GL_TEXTURE_2D, host.texture);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    host.image_target_texture =
        (PFNGLEGLIMAGETARGETTEXTURE2DOESPROC)eglGetProcAddress("glEGLImageTargetTexture2DOES");
}

static void draw_pending(void)
{
    if (!host.pending)
        return;
    struct wpe_fdo_egl_exported_image *image = host.pending;
    host.pending = NULL;
    host.image_target_texture(GL_TEXTURE_2D, wpe_fdo_egl_exported_image_get_egl_image(image));
    glClear(GL_COLOR_BUFFER_BIT);
    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
    uint32_t before = now_ms();
    SDL_GL_SwapWindow(host.window);
    if (host.trace_frames) {
        // Once a second: frames shown, the slowest swap, and the longest gap between two frames.
        static uint32_t window_start, frames, worst_swap, worst_gap, last;
        uint32_t now = now_ms();
        frames++;
        if (now - before > worst_swap) worst_swap = now - before;
        if (last && now - last > worst_gap) worst_gap = now - last;
        last = now;
        if (now - window_start >= 1000) {
            fprintf(stderr, "PRESENT frames=%u worst_swap=%u worst_gap=%u\n", frames, worst_swap, worst_gap);
            window_start = now;
            frames = worst_swap = worst_gap = 0;
        }
    }
    if (host.shown)
        wpe_view_backend_exportable_fdo_egl_dispatch_release_exported_image(host.exportable, host.shown);
    host.shown = image;
    wpe_view_backend_exportable_fdo_dispatch_frame_complete(host.exportable);
}

static uint32_t key_code(const SDL_Keysym *k)
{
    switch (k->sym) {
    case SDLK_LEFT: return WPE_KEY_Left;
    case SDLK_RIGHT: return WPE_KEY_Right;
    case SDLK_UP: return WPE_KEY_Up;
    case SDLK_DOWN: return WPE_KEY_Down;
    case SDLK_RETURN: return WPE_KEY_Return;
    case SDLK_BACKSPACE: return WPE_KEY_BackSpace;
    case SDLK_ESCAPE: return WPE_KEY_Escape;
    case SDLK_TAB: return WPE_KEY_Tab;
    case SDLK_PAGEUP: return WPE_KEY_Page_Up;
    case SDLK_PAGEDOWN: return WPE_KEY_Page_Down;
    case SDLK_HOME: return WPE_KEY_Home;
    case SDLK_END: return WPE_KEY_End;
    case SDLK_DELETE: return WPE_KEY_Delete;
    case SDLK_SPACE: return WPE_KEY_space;
    default: return 0;   // printable keys arrive as SDL_TEXTINPUT
    }
}

static void send_key(uint32_t code, uint32_t hw, bool pressed)
{
    struct wpe_input_keyboard_event e = {now_ms(), code, hw, pressed, 0};
    wpe_view_backend_dispatch_keyboard_event(host.backend, &e);
}

static void handle(const SDL_Event *ev)
{
    if (g_getenv("BROWSER_TRACE_INPUT")) {
        if (ev->type == SDL_KEYDOWN || ev->type == SDL_KEYUP)
            fprintf(stderr, "ev key %s sym=0x%x scan=%d\n", ev->type == SDL_KEYDOWN ? "down" : "up",
                    ev->key.keysym.sym, ev->key.keysym.scancode);
        else if (ev->type == SDL_TEXTINPUT)
            fprintf(stderr, "ev text '%s'\n", ev->text.text);
        else if (ev->type == SDL_TEXTEDITING)
            fprintf(stderr, "ev editing '%s' %d %d\n", ev->edit.text, ev->edit.start, ev->edit.length);
        else if (ev->type != SDL_MOUSEMOTION)
            fprintf(stderr, "ev type 0x%x\n", ev->type);
    }
    switch (ev->type) {
    case SDL_QUIT:
        host.quit = true;
        break;
    case SDL_KEYDOWN:
    case SDL_KEYUP:
        if (ev->key.keysym.scancode == SCANCODE_WEBOS_BACK) {
            // At the first page Back does nothing: the Home key leaves the app, and quitting on a
            // stray Back loses the page.
            if (ev->type == SDL_KEYUP) {
                gboolean can = webkit_web_view_can_go_back(host.view);
                fprintf(stderr, "back: can_go_back=%d\n", can);
                if (can)
                    webkit_web_view_go_back(host.view);
            }
        } else if (key_code(&ev->key.keysym)) {
            send_key(key_code(&ev->key.keysym), ev->key.keysym.scancode, ev->type == SDL_KEYDOWN);
        }
        break;
    case SDL_TEXTINPUT:          // only while a text field has focus, see TvInput
        g_signal_emit_by_name(host.input, "committed", ev->text.text);
        break;
    case SDL_MOUSEMOTION: {
        struct wpe_input_pointer_event e = {wpe_input_pointer_event_type_motion, now_ms(),
                                            to_view_x(ev->motion.x), to_view_y(ev->motion.y), 0, 0, 0};
        wpe_view_backend_dispatch_pointer_event(host.backend, &e);
        break;
    }
    case SDL_MOUSEBUTTONDOWN:
    case SDL_MOUSEBUTTONUP: {
        struct wpe_input_pointer_event e = {wpe_input_pointer_event_type_button, now_ms(),
                                            to_view_x(ev->button.x), to_view_y(ev->button.y), ev->button.button,
                                            ev->type == SDL_MOUSEBUTTONDOWN, 0};
        wpe_view_backend_dispatch_pointer_event(host.backend, &e);
        break;
    }
    case SDL_MOUSEWHEEL: {
        int x, y;
        SDL_GetMouseState(&x, &y);
        struct wpe_input_axis_event e = {wpe_input_axis_event_type_motion, now_ms(), to_view_x(x), to_view_y(y), 0,
                                         ev->wheel.y * 120, 0};
        wpe_view_backend_dispatch_axis_event(host.backend, &e);
        break;
    }
    }
}

static gboolean keep_polling_input(gpointer data) { return G_SOURCE_CONTINUE; }

// Launch param "then": a second URL opened once the first page finishes, so perf.py can time a
// navigation inside a warm web process, not only cold starts.
static char *then_url;

// User-path smoothness probe: one wheel notch down every 50 ms for 8 s, the way a mouse or the
// Magic Remote wheel scrolls (WebKit's scrolling thread, not the page's main thread). The frames
// that reach the screen meanwhile are the PRESENT lines before the closing "SCROLL mode=wheel".
static gboolean wheel_tick(gpointer data)
{
    static int ticks;
    struct wpe_input_axis_event e = {wpe_input_axis_event_type_motion, now_ms(), host.view_w / 2,
                                     host.view_h / 2, 0, -120, 0};
    wpe_view_backend_dispatch_axis_event(host.backend, &e);
    if (++ticks < 160)
        return G_SOURCE_CONTINUE;
    fprintf(stderr, "SCROLL mode=wheel\n");
    return G_SOURCE_REMOVE;
}

static gboolean wheel_start(gpointer data)
{
    g_timeout_add(50, wheel_tick, NULL);
    return G_SOURCE_REMOVE;
}

// A dead web process leaves a blank view; log it for perf.py and bring the page back, but only
// if the last crash was a minute ago: a page that crashes on load would otherwise loop forever.
static void on_web_process_terminated(WebKitWebView *view, WebKitWebProcessTerminationReason reason, gpointer data)
{
    static uint32_t last_reload;
    fprintf(stderr, "CRASH reason=%d %s\n", reason, webkit_web_view_get_uri(view));
    if (!last_reload || now_ms() - last_reload > 60000) {
        last_reload = now_ms();
        webkit_web_view_reload(view);
    }
}

// One "LOAD <ms> <uri>" line per navigation: the perf number for real pages, next to bench.html.
static void on_load_changed(WebKitWebView *view, WebKitLoadEvent event, gpointer data)
{
    static uint32_t started;
    if (event == WEBKIT_LOAD_STARTED)
        started = now_ms();
    else if (event == WEBKIT_LOAD_FINISHED) {
        fprintf(stderr, "LOAD %u %s\n", now_ms() - started, webkit_web_view_get_uri(view));
        if (host.wheel_probe) {
            host.wheel_probe = false;
            g_timeout_add(host.wheel_delay_ms, wheel_start, NULL);
        }
        if (then_url) {
            webkit_web_view_load_uri(view, then_url);
            g_clear_pointer(&then_url, g_free);
        }
    }
}

// Input method that ties WebKit's editable focus to SDL text input: focusing a text field opens
// the webOS on-screen keyboard, and whatever it (or a USB keyboard) types is committed as text, so
// non-Latin input works without mapping each character to a key code.
typedef struct { WebKitInputMethodContext parent; } TvInput;
typedef struct { WebKitInputMethodContextClass parent_class; } TvInputClass;
G_DEFINE_TYPE(TvInput, tv_input, WEBKIT_TYPE_INPUT_METHOD_CONTEXT)

static void tv_input_focus_in(WebKitInputMethodContext *context) { SDL_StartTextInput(); }
static void tv_input_focus_out(WebKitInputMethodContext *context) { SDL_StopTextInput(); }

static void tv_input_get_preedit(WebKitInputMethodContext *context, char **text, GList **underlines,
                                 guint *cursor_offset)
{
    if (text)
        *text = g_strdup("");
    if (underlines)
        *underlines = NULL;
    if (cursor_offset)
        *cursor_offset = 0;
}

static gboolean tv_input_filter_key_event(WebKitInputMethodContext *context, gpointer key_event)
{
    return FALSE;
}

static void tv_input_class_init(TvInputClass *klass)
{
    WebKitInputMethodContextClass *im = WEBKIT_INPUT_METHOD_CONTEXT_CLASS(klass);
    im->notify_focus_in = tv_input_focus_in;
    im->notify_focus_out = tv_input_focus_out;
    im->get_preedit = tv_input_get_preedit;
    im->filter_key_event = tv_input_filter_key_event;
}

static void tv_input_init(TvInput *self) {}

// SAM starts the binary itself (LS2 roles are keyed on its path), so there is no wrapper script:
// point WebKit, GStreamer, GIO and OpenSSL at the bundle from here, before any of them initialise.
static void use_bundle(void)
{
    char *exe = g_file_read_link("/proc/self/exe", NULL);
    char *dir = g_path_get_dirname(exe);
    struct { const char *var, *sub; } env[] = {
        {"WEBKIT_EXEC_PATH", "libexec"},
        {"GST_PLUGIN_SYSTEM_PATH", "lib/gstreamer-1.0"},
        {"GIO_MODULE_DIR", "lib/gio/modules"},
        {"SSL_CERT_FILE", "etc/ssl/certs/ca-certificates.crt"},
        {"FONTCONFIG_FILE", "etc/fonts/fonts.conf"},   // the TV's lacks generic aliases, see the file
    };
    for (size_t i = 0; i < G_N_ELEMENTS(env); i++) {
        char *path = g_build_filename(dir, env[i].sub, NULL);
        g_setenv(env[i].var, path, TRUE);
        g_free(path);
    }
    // webOS exports the versioned GST_*_1_0 variables, which win over the plain ones, pointing at
    // LG's own plugins built for its patched GStreamer 1.16; loading them next to ours corrupts the
    // type system. Its registry policy (UPDATE=no) and old plugin scanner must go as well.
    static const char *gst_unset[] = {"GST_PLUGIN_PATH", "GST_PLUGIN_PATH_1_0", "GST_PLUGIN_SCANNER",
                                      "GST_PLUGIN_SCANNER_1_0", "GST_REGISTRY_UPDATE"};
    for (size_t i = 0; i < G_N_ELEMENTS(gst_unset); i++)
        g_unsetenv(gst_unset[i]);
    g_setenv("GST_PLUGIN_SYSTEM_PATH_1_0", g_getenv("GST_PLUGIN_SYSTEM_PATH"), TRUE);
    g_setenv("GST_REGISTRY", "/tmp/browser-gst-registry.bin", TRUE);   // the app dir is read-only
    g_setenv("GST_REGISTRY_1_0", "/tmp/browser-gst-registry.bin", TRUE);
    g_setenv("GST_REGISTRY_FORK", "no", TRUE);                          // no scanner binary bundled
    g_setenv("XDG_CACHE_HOME", "/tmp/browser-cache", TRUE);
    // webOS exports GIO_EXTRA_MODULES=/usr/lib/gio/modules; its gnutls module is built for the TV's
    // older GLib and breaks ours, so only the bundled OpenSSL TLS backend may load.
    g_unsetenv("GIO_EXTRA_MODULES");
    g_setenv("GIO_USE_TLS", "openssl", TRUE);
    // Read by our WebKit patch 0007. A cross-site swap starts a cold web process (no JIT code, no
    // caches) and keeps the old one alive for back/forward: two 200+ MB processes on a TV with
    // ~600 MB free. One process for every site keeps both speed and memory.
    g_setenv("WEBKIT_DISABLE_PSON", "1", TRUE);
    // bmalloc on this softfp/kernel-4.4 TV hands JSC butterflies that straddle the end of a mapped
    // 1 MB region, and the web process segfaults in allocateMoreOutOfLineStorage (Speedometer
    // within minutes, real sites now and then). Malloc=1 routes bmalloc to glibc malloc: no crash,
    // speed unchanged within noise.
    g_setenv("Malloc", "1", TRUE);
    // With Malloc=1 every WebKit allocation lands in the system malloc, so mimalloc preloaded into
    // the processes this host spawns replaces glibc's: Speedometer +11%, page loads 4-9% faster for
    // 5-12% more RSS on the C1. Launch param env=LD_PRELOAD= A/Bs it against glibc.
    char *mimalloc = g_build_filename(dir, "lib", "libmimalloc.so.2", NULL);
    if (g_file_test(mimalloc, G_FILE_TEST_EXISTS))
        g_setenv("LD_PRELOAD", mimalloc, FALSE);
    g_free(mimalloc);
    // JSC keeps the RegExp JIT off on 32-bit; with our patches 0010-0012 its ARMv7 path works and
    // regexps run ~5x faster. Not overwritten, so launch param env=JSC_useRegExpJIT=false A/Bs it.
    g_setenv("JSC_useRegExpJIT", "true", FALSE);
    g_free(dir);
    g_free(exe);
}

// SAM passes launch params as one JSON argument, e.g. {"url":"https://...","then":"https://..."}.
// Only flat string fields without escapes are read, so a scan is enough and json-glib is not bundled.
static char *launch_param(const char *arg, const char *name)
{
    if (!arg || arg[0] != '{')
        return NULL;
    char *quoted = g_strdup_printf("\"%s\"", name);
    const char *key = strstr(arg, quoted);
    const char *start = key ? strchr(key + strlen(quoted), '"') : NULL;
    const char *end = start ? strchr(start + 1, '"') : NULL;
    g_free(quoted);
    return end ? g_strndup(start + 1, end - start - 1) : NULL;
}

int main(int argc, char **argv)
{
    const char *arg = argc > 1 ? argv[1] : NULL;
    const char *url = launch_param(arg, "url");
    if (!url)
        url = arg && arg[0] != '{' ? arg : "https://www.google.com";
    then_url = launch_param(arg, "then");
    // Child processes inherit this: a crashing web process writes a 300-580 MB core into the
    // app dir and fills the developer partition. Launch param core=1 keeps them for debugging.
    char *core = launch_param(arg, "core");
    if (!core) {
        struct rlimit none = {0, 0};
        setrlimit(RLIMIT_CORE, &none);
    }
    g_free(core);
    char *view = launch_param(arg, "view");   // e.g. "1920x1080"
    int w, h;
    if (view && sscanf(view, "%dx%d", &w, &h) == 2 && w > 0 && h > 0) {
        host.view_w = w;
        host.view_h = h;
    }
    g_free(view);
    // Launch param "env": "NAME=value,NAME=value" set before WebKit starts, for A/B runs of
    // WebKit's own tunables (WEBKIT_SKIA_*, JSC_*) without a rebuild.
    char *env = launch_param(arg, "env");
    if (env) {
        char **pairs = g_strsplit(env, ",", -1);
        for (char **p = pairs; *p; p++) {
            char *eq = strchr(*p, '=');
            if (eq) {
                *eq = '\0';
                g_setenv(*p, eq + 1, TRUE);
            }
        }
        g_strfreev(pairs);
        g_free(env);
    }
    // SAM drops a native app's stderr; the web and network processes inherit this fd too.
    // Appended, not truncated: when memchute kills the app under memory pressure, surface-manager
    // relaunches it with no params, and the killed run's log must survive that. bench.py truncates.
    struct stat log_st;
    bool log_big = stat("/tmp/browser.log", &log_st) == 0 && log_st.st_size > 8 << 20;
    freopen("/tmp/browser.log", log_big ? "w" : "a", stderr);
    setvbuf(stderr, NULL, _IOLBF, 0);
    fprintf(stderr, "START pid=%d %s\n", getpid(), arg ? arg : "");
    dup2(fileno(stderr), fileno(stdout));
    setvbuf(stdout, NULL, _IOLBF, 0);
    use_bundle();

    SDL_LogSetAllPriority(SDL_LOG_PRIORITY_VERBOSE);
    // Without it webOS keeps Back for itself and offers to close the app; with it Back reaches
    // the app as scancode 482 and walks the history.
    SDL_SetHint(SDL_HINT_WEBOS_ACCESS_POLICY_KEYS_BACK, "true");
    if (SDL_Init(SDL_INIT_VIDEO) != 0) {
        fprintf(stderr, "SDL_Init: %s\n", SDL_GetError());
        return 1;
    }
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_ES);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 2);
    SDL_GL_SetAttribute(SDL_GL_ALPHA_SIZE, 8);
    host.window = SDL_CreateWindow("browser", 0, 0, WIDTH, HEIGHT, SDL_WINDOW_OPENGL | SDL_WINDOW_FULLSCREEN);
    if (!host.window || !SDL_GL_CreateContext(host.window)) {
        fprintf(stderr, "window: %s\n", SDL_GetError());
        return 1;
    }
    SDL_GL_SetSwapInterval(1);
    gl_setup();

    wpe_loader_init("libWPEBackend-fdo-1.0.so.1");
    if (!wpe_fdo_initialize_for_egl_display(eglGetCurrentDisplay())) {
        fprintf(stderr, "wpe_fdo_initialize_for_egl_display failed\n");
        return 1;
    }
    static const struct wpe_view_backend_exportable_fdo_egl_client client = {.export_fdo_egl_image = on_frame};
    host.exportable = wpe_view_backend_exportable_fdo_egl_create(&client, NULL, host.view_w, host.view_h);
    host.backend = wpe_view_backend_exportable_fdo_get_view_backend(host.exportable);

    WebKitWebViewBackend *view_backend = webkit_web_view_backend_new(host.backend, NULL, NULL);
    WebKitSettings *settings = webkit_settings_new_with_settings(
        "enable-spatial-navigation", TRUE,          // arrow keys walk links and controls, like a TV UI
        "enable-mediasource", TRUE,
        "enable-webgl", TRUE,
        "enable-developer-extras", TRUE,
        "enable-write-console-messages-to-stdout", TRUE,   // page console.log lands in the log
        // Desktop Safari: with a "Web0S; SmartTV" UA Google serves its legacy basic-HTML pages.
        "user-agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                      "(KHTML, like Gecko) Version/18.0 Safari/605.1.15",
        NULL);
    WebKitUserContentManager *content = webkit_user_content_manager_new();
    char *autoscroll = launch_param(arg, "autoscroll");
    if (autoscroll && !strcmp(autoscroll, "wheel")) {
        host.trace_frames = true;
        host.wheel_probe = true;
        // Heavy apps keep the main thread busy well after load (YouTube ~20 s); a later start
        // measures scrolling a settled page rather than scrolling during start-up.
        char *delay = launch_param(arg, "wheeldelay");
        host.wheel_delay_ms = delay ? (unsigned)atoi(delay) : 2000;
        g_free(delay);
        g_free(autoscroll);
    } else if (autoscroll) {
        host.trace_frames = true;
        // Smoothness probe for perf.py: 2 s after load, scroll 8 px per animation frame for 8 s and
        // log the frame rate and the frames that took over 25 ms (a missed 60 Hz frame and more).
        static const char *probe =
            "addEventListener('load', () => setTimeout(() => {"
            " const t0 = performance.now(); let last = t0, n = 0, slow = 0, worst = 0;"
            " function step(t) { const d = t - last; last = t; n++; if (d > 25) slow++; if (d > worst) worst = d;"
            "  scrollBy(0, 8);"
            "  if (t - t0 < 8000) requestAnimationFrame(step);"
            "  else console.log('SCROLL fps=' + (n * 1000 / (t - t0)).toFixed(1) + ' slow=' + slow + ' worst=' + worst.toFixed(0)); }"
            " requestAnimationFrame(step); }, 2000));";
        webkit_user_content_manager_add_script(content, webkit_user_script_new(probe,
            WEBKIT_USER_CONTENT_INJECT_TOP_FRAME, WEBKIT_USER_SCRIPT_INJECT_AT_DOCUMENT_START, NULL, NULL));
        g_free(autoscroll);
    }
    char *click = launch_param(arg, "click");
    if (click) {
        // Start button for suites without an auto-start URL parameter (MotionMark): click the CSS
        // selector once it exists and is enabled; MotionMark keeps its button disabled while it
        // measures the frame rate, and a click on a disabled button is silently dropped.
        char *selector = g_strescape(click, NULL);
        char *script = g_strdup_printf(
            "if (window.top === window) addEventListener('load', () => { const t0 = Date.now();"
            " const timer = setInterval(() => { const e = document.querySelector(\"%s\");"
            " if (e && !e.disabled) { clearInterval(timer); console.log('CLICK ok ' + (Date.now() - t0)); e.click(); }"
            " else if (Date.now() - t0 > 60000) { clearInterval(timer); console.log('CLICK ' + (e ? 'disabled' : 'missing')); }"
            " }, 500); });", selector);
        webkit_user_content_manager_add_script(content, webkit_user_script_new(script,
            WEBKIT_USER_CONTENT_INJECT_TOP_FRAME, WEBKIT_USER_SCRIPT_INJECT_AT_DOCUMENT_START, NULL, NULL));
        g_free(script);
        g_free(selector);
        g_free(click);
    }
    char *probe = launch_param(arg, "probe");
    if (probe) {
        // Score probe for third-party benchmarks (Speedometer, JetStream, MotionMark): poll the CSS
        // selector of the page's final score every 5 s and log "PROBE <seconds> <text>" once it shows
        // a number, so perf.py reads it from the log like our own probes.
        char *selector = g_strescape(probe, NULL);
        char *script = g_strdup_printf(
            "if (window.top === window) addEventListener('load', () => { const t0 = Date.now();"
            " const timer = setInterval(() => { const e = document.querySelector(\"%s\");"
            "  const text = e && e.textContent.trim();"
            "  if (text && /[0-9]/.test(text)) { clearInterval(timer);"
            "   console.log('PROBE ' + Math.round((Date.now() - t0) / 1000) + ' ' + text); } }, 5000); });",
            selector);
        webkit_user_content_manager_add_script(content, webkit_user_script_new(script,
            WEBKIT_USER_CONTENT_INJECT_TOP_FRAME, WEBKIT_USER_SCRIPT_INJECT_AT_DOCUMENT_START, NULL, NULL));
        g_free(script);
        g_free(selector);
        g_free(probe);
    }
    char *watch = launch_param(arg, "watch");
    if (watch) {
        // Progress marker for long suites: log "WATCH <unix s> <text>" whenever the text of the CSS
        // selector changes (JetStream: the running test), to line up with memory samples by clock.
        char *selector = g_strescape(watch, NULL);
        char *script = g_strdup_printf(
            "if (window.top === window) addEventListener('load', () => { let last = null;"
            " setInterval(() => { const e = document.querySelector(\"%s\");"
            "  const text = e ? e.textContent.trim().split(/\\s+/)[0] : '';"
            "  if (text !== last) { last = text; console.log('WATCH ' + Math.round(Date.now() / 1000) + ' ' + text); }"
            " }, 1000); });", selector);
        webkit_user_content_manager_add_script(content, webkit_user_script_new(script,
            WEBKIT_USER_CONTENT_INJECT_TOP_FRAME, WEBKIT_USER_SCRIPT_INJECT_AT_DOCUMENT_START, NULL, NULL));
        g_free(script);
        g_free(selector);
        g_free(watch);
    }
    host.view =WEBKIT_WEB_VIEW(g_object_new(WEBKIT_TYPE_WEB_VIEW, "backend", view_backend,
                                             "settings", settings, "user-content-manager", content, NULL));
    host.input = WEBKIT_INPUT_METHOD_CONTEXT(g_object_new(tv_input_get_type(), NULL));
    webkit_web_view_set_input_method_context(host.view, host.input);
    SDL_StopTextInput();          // SDL starts with text input on; the keyboard opens on field focus
    g_signal_connect(host.view, "load-changed", G_CALLBACK(on_load_changed), NULL);
    g_signal_connect(host.view, "web-process-terminated", G_CALLBACK(on_web_process_terminated), NULL);
    webkit_web_view_load_uri(host.view, url);

    GMainContext *ctx = g_main_context_default();
    // SDL's Wayland fd is not a GLib source, so the blocking wait below must wake for input too.
    g_timeout_add(8, keep_polling_input, NULL);
    while (!host.quit) {
        SDL_Event ev;
        while (SDL_PollEvent(&ev))
            handle(&ev);
        while (g_main_context_iteration(ctx, FALSE)) {}
        draw_pending();
        if (!host.pending)
            g_main_context_iteration(ctx, TRUE);   // sleep until WebKit or a timer wakes us
    }
    return 0;
}
