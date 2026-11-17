// Hardware video on the LG TV through the cr120 launcher (browser/cr120/launcher/cr120run.c), which drives LG's
// NDL DirectMedia. From WebOS-Chromium (github.com/sarahahzub/WebOS-Chromium, BSD-3) patch 0023.
#ifndef CONTENT_RENDERER_MEDIA_CN_NDL_RENDERER_H_
#define CONTENT_RENDERER_MEDIA_CN_NDL_RENDERER_H_

#include <memory>

#include "base/memory/raw_ptr.h"
#include "media/base/renderer_factory.h"

namespace media {
class MediaLog;
}

namespace content {

// Wraps the normal RendererImplFactory. Each renderer it makes uses the hardware path when the stream suits it
// (H.264/HEVC/VP9/AV1 video, clear, launcher socket reachable) and otherwise behaves exactly like RendererImpl.
class CnNdlRendererFactory : public media::RendererFactory {
 public:
  CnNdlRendererFactory(std::unique_ptr<media::RendererFactory> fallback, media::MediaLog* media_log);
  ~CnNdlRendererFactory() override;

  // True when the launcher exported $CN_MEDIA_SOCK.
  static bool Enabled();

  std::unique_ptr<media::Renderer> CreateRenderer(
      const scoped_refptr<base::SequencedTaskRunner>& media_task_runner,
      const scoped_refptr<base::TaskRunner>& worker_task_runner,
      media::AudioRendererSink* audio_renderer_sink,
      media::VideoRendererSink* video_renderer_sink,
      media::RequestOverlayInfoCB request_overlay_info_cb,
      const gfx::ColorSpace& target_color_space) override;

 private:
  std::unique_ptr<media::RendererFactory> fallback_;
  raw_ptr<media::MediaLog> media_log_;
};

}  // namespace content

#endif  // CONTENT_RENDERER_MEDIA_CN_NDL_RENDERER_H_
