"""Edits a copy of the tree (argv[1]) for patch 0015: NDL hardware video wiring outside the new files."""
import sys
root = sys.argv[1]

def edit(path, old, new, count=1):
    p = f"{root}/{path}"
    s = open(p).read()
    assert s.count(old) == count, (path, old[:60], s.count(old))
    open(p, "w").write(s.replace(old, new))

edit("ozone/wayland/display.h",
     "  wl_registry* registry() const { return registry_; }\n",
     "  wl_registry* registry() const { return registry_; }\n\n"
     "  // The browser windows by handle (cn_video_export.cc exports the video plane from the first one).\n"
     "  const WindowMap& windows() const { return widget_map_; }\n")
edit("ozone/wayland/display.cc",
     "  StartProcessingEvents();\n",
     "  StartProcessingEvents();\n  CnVideoExportStart(this);\n")
edit("ozone/wayland/display.cc",
     '#if defined(USE_DATA_DEVICE_MANAGER)\n#include "ozone/wayland/data_device.h"\n',
     '#include "ozone/wayland/foreign_window/cn_video_export.h"\n\n#if defined(USE_DATA_DEVICE_MANAGER)\n#include "ozone/wayland/data_device.h"\n')
edit("ozone/wayland/BUILD.gn",
     '  if (use_neva_media) {\n    deps += [ "//ui/platform_window:mojom" ]\n',
     '  # Hardware video through the cr120 launcher (NDL): exports the video plane, places it at the hole.\n'
     '  sources += [\n    "foreign_window/cn_video_export.cc",\n    "foreign_window/cn_video_export.h",\n  ]\n'
     '  if (use_neva_media) {\n    deps += [ "//ui/platform_window:mojom" ]\n')
# The window's appId must be the app's, or LSM does not tie the exported video plane to our app.
edit("ozone/wayland/window.cc",
     "  std::string kAppWindowId = strs.str();\n",
     "  std::string kAppWindowId = getenv(\"APPID\") ? getenv(\"APPID\") : strs.str();\n")
# An opaque region makes LSM hide the video plane under the window (audio plays, picture black).
edit("ozone/wayland/window.cc",
     "  if (opacity_ == ui::PlatformWindowOpacity::kOpaqueWindow)\n#endif  // defined(OS_WEBOS)\n    wl_surface_set_opaque_region",
     "  if (opacity_ == ui::PlatformWindowOpacity::kOpaqueWindow)\n#endif  // defined(OS_WEBOS)\n  if (!CnHardwareVideo())\n    wl_surface_set_opaque_region",
     count=2)
edit("ozone/wayland/window.cc",
     '#include "ozone/wayland/window.h"\n',
     '#include "ozone/wayland/window.h"\n\n#include <cstdlib>\n\n#include "ozone/wayland/foreign_window/cn_video_export.h"\n')
edit("content/renderer/BUILD.gn",
     '    "media/inspector_media_event_handler.h",\n',
     '    "media/inspector_media_event_handler.h",\n    "media/cn_ndl_renderer.cc",\n    "media/cn_ndl_renderer.h",\n')
edit("content/renderer/media/media_factory.cc",
     '#include "content/renderer/media/media_factory.h"\n',
     '#include "content/renderer/media/media_factory.h"\n\n#include "content/renderer/media/cn_ndl_renderer.h"\n')
edit("content/renderer/media/media_factory.cc",
     "    factory_selector->AddBaseFactory(RendererType::kRendererImpl,\n                                     std::move(renderer_impl_factory));\n  }\n",
     "    // Hardware video through the cr120 launcher (NDL) when it exported $CN_MEDIA_SOCK; streams NDL cannot take\n"
     "    // still go to RendererImpl inside CnNdlRenderer.\n"
     "    if (CnNdlRendererFactory::Enabled()) {\n"
     "      factory_selector->AddBaseFactory(\n"
     "          RendererType::kRendererImpl,\n"
     "          std::make_unique<CnNdlRendererFactory>(std::move(renderer_impl_factory), media_log));\n"
     "    } else {\n"
     "      factory_selector->AddBaseFactory(RendererType::kRendererImpl,\n"
     "                                       std::move(renderer_impl_factory));\n"
     "    }\n  }\n")
print("ok")
