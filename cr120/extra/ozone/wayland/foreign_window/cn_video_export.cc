// Hardware video through LG's NDL, window side. The TV shows NDL's picture on a video plane under our window, and
// LSM shows that plane only for a video window exported from the app window's own surface (one exported from the
// launcher's separate Wayland connection stays black). So this GPU-process code, which owns the Wayland connection
// in this ozone backend, exports it, sends the window id to the launcher over $CN_MEDIA_SOCK (WINID, the launcher
// passes it to NDL_DirectMediaSetWindowId), and moves the plane to the video hole that viz reports each frame.
// Adapted from WebOS-Chromium (github.com/sarahahzub/WebOS-Chromium, BSD-3) patch 0025 for the Intel ozone backend.

#include "ozone/wayland/foreign_window/cn_video_export.h"

#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#include <atomic>
#include <cstdlib>
#include <cstring>
#include <string>

#include "base/functional/bind.h"
#include "base/logging.h"
#include "base/task/single_thread_task_runner.h"
#include "base/time/time.h"
#include "ozone/wayland/display.h"
#include "ozone/wayland/shell/shell_surface.h"
#include "ozone/wayland/window.h"
#include "ui/gfx/geometry/rect.h"
#include "ui/gfx/geometry/size.h"
#include "wayland-webos-foreign-client-protocol.h"

namespace ozonewayland {
namespace {

// Launcher protocol (browser/cr120/launcher/cr120run.c): header {type, payload length}.
constexpr uint32_t kGeometry = 5, kWindowId = 7, kVideoSize = 8;

struct CnVideoExport {
  WaylandDisplay* display = nullptr;
  // This build binds no wl_webos_foreign (USE_GAV is off), so the export binds its own on a private queue:
  // its roundtrips then never dispatch the display's other events out of turn.
  wl_event_queue* queue = nullptr;
  wl_webos_foreign* foreign = nullptr;
  scoped_refptr<base::SingleThreadTaskRunner> task_runner;
  wl_webos_exported* exported = nullptr;
  int fd = -1;
  int tries = 0;
  gfx::Rect last_dst;
  gfx::Size last_src, video_size;
};
CnVideoExport* g_cn = nullptr;
std::atomic<bool> g_cn_ready{false};

// The video plane covers the whole panel until the first hole arrives: NDL shows nothing on a muted, unplaced window.
void PlaceFullScreen() {
  wl_compositor* compositor = g_cn->display->GetCompositor();
  wl_region* src = wl_compositor_create_region(compositor);
  wl_region_add(src, 0, 0, 1920, 1080);
  wl_region* dst = wl_compositor_create_region(compositor);
  wl_region_add(dst, 0, 0, 1920, 1080);
  wl_webos_exported_set_exported_window(g_cn->exported, src, dst);
  wl_region_destroy(dst);
  wl_region_destroy(src);
  wl_webos_exported_set_property(g_cn->exported, "mute", "off");
  g_cn->display->FlushDisplay();
}

void OnAssigned(void* data, wl_webos_exported* exported, const char* window_id, uint32_t exported_type) {
  const std::string id = window_id ? window_id : "";
  LOG(WARNING) << "cn-ndl: video window id " << id;
  int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
  sockaddr_un a{};
  a.sun_family = AF_UNIX;
  strncpy(a.sun_path, getenv("CN_MEDIA_SOCK"), sizeof(a.sun_path) - 1);
  if (fd < 0 || connect(fd, reinterpret_cast<sockaddr*>(&a), sizeof(a)) != 0) {
    PLOG(ERROR) << "cn-ndl: launcher socket";
    if (fd >= 0) {
      close(fd);
    }
    return;
  }
  const uint32_t hdr[2] = {kWindowId, static_cast<uint32_t>(id.size())};
  if (send(fd, hdr, sizeof(hdr), MSG_NOSIGNAL) != sizeof(hdr) ||
      send(fd, id.data(), id.size(), MSG_NOSIGNAL) != static_cast<ssize_t>(id.size())) {
    PLOG(ERROR) << "cn-ndl: window id to launcher";
    close(fd);
    return;
  }
  g_cn->fd = fd;
  PlaceFullScreen();
  g_cn_ready.store(true, std::memory_order_release);
}

void OnGlobal(void* data, wl_registry* registry, uint32_t name, const char* interface, uint32_t version) {
  if (!strcmp(interface, "wl_webos_foreign")) {
    g_cn->foreign =
        static_cast<wl_webos_foreign*>(wl_registry_bind(registry, name, &wl_webos_foreign_interface, 1));
  }
}
void OnGlobalRemove(void* data, wl_registry* registry, uint32_t name) {}

bool BindForeign() {
  wl_display* dpy = g_cn->display->display();
  g_cn->queue = wl_display_create_queue(dpy);
  wl_registry* registry = wl_display_get_registry(dpy);
  wl_proxy_set_queue(reinterpret_cast<wl_proxy*>(registry), g_cn->queue);
  static const wl_registry_listener kRegistryListener = {&OnGlobal, &OnGlobalRemove};
  wl_registry_add_listener(registry, &kRegistryListener, nullptr);
  wl_display_roundtrip_queue(dpy, g_cn->queue);
  wl_registry_destroy(registry);
  LOG_IF(ERROR, !g_cn->foreign) << "cn-ndl: the compositor has no wl_webos_foreign";
  return g_cn->foreign != nullptr;
}

void TryExport() {
  if (!g_cn->foreign && !BindForeign()) {
    return;
  }
  WaylandShellSurface* shell = nullptr;
  for (const auto& [handle, window] : g_cn->display->windows()) {
    if (window && window->ShellSurface() && window->ShellSurface()->GetWLSurface()) {
      shell = window->ShellSurface();
      break;
    }
  }
  if (!shell) {
    if (++g_cn->tries < 240) {
      g_cn->task_runner->PostDelayedTask(FROM_HERE, base::BindOnce(&TryExport), base::Milliseconds(500));
    }
    return;
  }
  g_cn->exported = wl_webos_foreign_export_element(g_cn->foreign, shell->GetWLSurface(),
                                                   WL_WEBOS_FOREIGN_WEBOS_EXPORTED_TYPE_VIDEO_OBJECT);
  static const wl_webos_exported_listener kListener = {&OnAssigned};
  wl_webos_exported_add_listener(g_cn->exported, &kListener, nullptr);
  LOG(WARNING) << "cn-ndl: exporting the video window from the browser window surface";
  // The window id event comes on our queue (the exported object inherits it from g_cn->foreign).
  for (int i = 0; i < 50 && !g_cn_ready.load(std::memory_order_acquire); ++i) {
    wl_display_roundtrip_queue(g_cn->display->display(), g_cn->queue);
  }
}

void SetGeometry(const gfx::Rect& dst) {
  for (;;) {  // VSIZE from the launcher, one per new stream; never block the GPU thread
    uint32_t m[4];
    if (recv(g_cn->fd, m, sizeof(m), MSG_DONTWAIT | MSG_PEEK) < static_cast<ssize_t>(sizeof(m))) {
      break;
    }
    recv(g_cn->fd, m, sizeof(m), MSG_DONTWAIT);
    if (m[0] == kVideoSize && m[1] == 8) {
      g_cn->video_size = gfx::Size(static_cast<int>(m[2]), static_cast<int>(m[3]));
    }
  }
  const gfx::Size src = g_cn->video_size.IsEmpty() ? dst.size() : g_cn->video_size;
  if (dst == g_cn->last_dst && src == g_cn->last_src) {
    return;
  }
  g_cn->last_dst = dst;
  g_cn->last_src = src;
  wl_compositor* compositor = g_cn->display->GetCompositor();
  wl_region* source_region = wl_compositor_create_region(compositor);
  wl_region_add(source_region, 0, 0, src.width(), src.height());
  wl_region* dest_region = wl_compositor_create_region(compositor);
  wl_region_add(dest_region, dst.x(), dst.y(), dst.width(), dst.height());
  wl_webos_exported_set_exported_window(g_cn->exported, source_region, dest_region);
  wl_region_destroy(dest_region);
  wl_region_destroy(source_region);
  g_cn->display->FlushDisplay();
  struct {
    uint32_t type, len;
    uint64_t token[2];
    int32_t x, y, w, h;
  } m = {kGeometry, 32, {0, 0}, dst.x(), dst.y(), dst.width(), dst.height()};
  if (send(g_cn->fd, &m, sizeof(m), MSG_DONTWAIT | MSG_NOSIGNAL) != static_cast<ssize_t>(sizeof(m))) {
    LOG(WARNING) << "cn-ndl: geometry to launcher failed";
  }
  LOG(WARNING) << "cn-ndl: video plane src " << src.ToString() << " -> " << dst.ToString();
}

}  // namespace

bool CnHardwareVideo() {
  static const bool on = getenv("CN_MEDIA_SOCK") && *getenv("CN_MEDIA_SOCK");
  return on;
}

void CnVideoExportStart(WaylandDisplay* display) {
  if (g_cn || !CnHardwareVideo()) {
    return;
  }
  g_cn = new CnVideoExport();
  g_cn->display = display;
  g_cn->task_runner = base::SingleThreadTaskRunner::GetCurrentDefault();
  g_cn->task_runner->PostDelayedTask(FROM_HERE, base::BindOnce(&TryExport), base::Milliseconds(500));
}

}  // namespace ozonewayland

// Called by viz (DirectRenderer, patch 0014) for each frame that has a video hole, on the viz thread.
extern "C" void cn_video_hole_geometry(int x, int y, int w, int h) {
  if (!ozonewayland::g_cn_ready.load(std::memory_order_acquire)) {
    return;
  }
  ozonewayland::g_cn->task_runner->PostTask(FROM_HERE,
                                            base::BindOnce(&ozonewayland::SetGeometry, gfx::Rect(x, y, w, h)));
}
