// Lists the Wayland globals the C1 compositor advertises (interface and version).
// usage on the TV: XDG_RUNTIME_DIR=/tmp/xdg WAYLAND_DISPLAY=wayland-0 ./wlglobals
#include <stdio.h>
#include <wayland-client.h>

static void global_add(void *d, struct wl_registry *r, uint32_t name, const char *iface,
                       uint32_t version) {
  printf("%s %u\n", iface, version);
}
static void global_remove(void *d, struct wl_registry *r, uint32_t name) {}
static const struct wl_registry_listener listener = {global_add, global_remove};

int main(void) {
  struct wl_display *dpy = wl_display_connect(NULL);
  if (!dpy) { fprintf(stderr, "no display\n"); return 1; }
  wl_registry_add_listener(wl_display_get_registry(dpy), &listener, NULL);
  wl_display_roundtrip(dpy);
  wl_display_disconnect(dpy);
  return 0;
}
