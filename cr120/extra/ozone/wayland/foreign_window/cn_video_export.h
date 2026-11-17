// Hardware video through LG's NDL, window side: see cn_video_export.cc.
#ifndef OZONE_WAYLAND_FOREIGN_WINDOW_CN_VIDEO_EXPORT_H_
#define OZONE_WAYLAND_FOREIGN_WINDOW_CN_VIDEO_EXPORT_H_

namespace ozonewayland {

class WaylandDisplay;

// True when the cr120 launcher exported $CN_MEDIA_SOCK (it owns NDL).
bool CnHardwareVideo();

// Starts exporting the video window once the display has a browser window. Call on the display's thread, after the
// registry globals are bound. Does nothing without $CN_MEDIA_SOCK.
void CnVideoExportStart(WaylandDisplay* display);

}  // namespace ozonewayland

#endif  // OZONE_WAYLAND_FOREIGN_WINDOW_CN_VIDEO_EXPORT_H_
