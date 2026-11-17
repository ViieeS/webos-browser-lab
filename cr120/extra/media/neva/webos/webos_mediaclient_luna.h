// WebOSMediaClient for the LG C1 (webOS 6) that drives uMediaServer (luna://com.webos.media) by
// spawning /usr/bin/luna-send, the one LS2 client a non-SAM root process may use.
// It replaces UMediaClientImpl, which derives from the TV's libumedia_api C++ class (libstdc++ ABI,
// not linkable into this libc++ build). Calls run on the thread pool; the "subscribe" stream is a
// long-lived `luna-send -i` whose stdout is read on a pool worker. Every event is handled on
// |main_task_runner_|.

#ifndef MEDIA_NEVA_WEBOS_WEBOS_MEDIACLIENT_LUNA_H_
#define MEDIA_NEVA_WEBOS_WEBOS_MEDIACLIENT_LUNA_H_

#include <memory>
#include <string>

#include "base/memory/weak_ptr.h"
#include "base/process/process.h"
#include "base/task/single_thread_task_runner.h"
#include "base/values.h"
#include "media/base/pipeline.h"
#include "media/base/ranges.h"
#include "media/neva/webos/webos_mediaclient.h"

namespace media {

class WebOSMediaClientLuna : public WebOSMediaClient {
 public:
  WebOSMediaClientLuna(
      const scoped_refptr<base::SingleThreadTaskRunner>& main_task_runner,
      base::WeakPtr<WebOSMediaClient::EventListener> event_listener,
      const std::string& app_id);
  WebOSMediaClientLuna(const WebOSMediaClientLuna&) = delete;
  WebOSMediaClientLuna& operator=(const WebOSMediaClientLuna&) = delete;
  ~WebOSMediaClientLuna() override;

  void Load(bool video,
            double current_time,
            bool is_local_source,
            const std::string& url,
            const std::string& mime_type,
            const std::string& referrer,
            const std::string& user_agent,
            const std::string& cookies,
            const std::string& payload) override;
  void Seek(base::TimeDelta time,
            const media::PipelineStatusCB& seek_cb) override;
  float GetPlaybackRate() const override { return playback_rate_; }
  void SetPlaybackRate(float playback_rate) override;
  double GetPlaybackVolume() const override { return volume_; }
  void SetPlaybackVolume(double volume, bool forced = false) override;
  bool SelectTrack(const MediaTrackType type, const std::string& id) override {
    return false;
  }
  void Suspend(SuspendReason reason) override;
  void Resume() override;
  bool IsRecoverableOnResume() override { return true; }
  void SetPreload(Preload preload) override {}
  bool IsPreloadable(const std::string& content_media_option) override {
    return false;
  }
  std::string MediaId() override { return media_id_; }
  double GetDuration() const override { return duration_; }
  void SetDuration(double duration) override { duration_ = duration; }
  double GetCurrentTime() override { return current_time_; }
  void SetCurrentTime(double time) override { current_time_ = time; }
  media::Ranges<base::TimeDelta> GetBufferedTimeRanges() const override;
  bool HasAudio() override { return has_audio_; }
  bool HasVideo() override { return has_video_; }
  gfx::Size GetCodedVideoSize() override { return natural_video_size_; }
  gfx::Size GetNaturalVideoSize() override { return natural_video_size_; }
  void SetNaturalVideoSize(const gfx::Size& size) override {
    natural_video_size_ = size;
  }
  bool DidLoadingProgress() override;
  bool UsesIntrinsicSize() const override { return true; }
  void Unload() override;
  bool IsSupportedBackwardTrickPlay() override { return false; }
  bool IsSupportedPreload() override { return false; }
  void SetDisableAudio(bool disable) override { audio_disabled_ = disable; }
  void SetMediaLayerId(const std::string& media_layer_id) override {
    media_layer_id_ = media_layer_id;
  }

 private:
  enum class State { kIdle, kLoading, kLoaded };

  std::string BuildLoadPayload() const;
  void LoadNow();
  void OnLoaded(const std::string& reply);
  void Call(const std::string& method, base::Value::Dict params);
  void StopSubscription();
  void OnEvent(const std::string& line);
  void HandleSourceInfo(const base::Value::Dict& info);
  void HandleVideoSize(int width, int height);
  void HandleError(int code, const std::string& text);
  void SignalLoadCompleted();

  const scoped_refptr<base::SingleThreadTaskRunner> main_task_runner_;
  base::WeakPtr<WebOSMediaClient::EventListener> event_listener_;
  std::string app_id_;

  std::string url_;
  std::string referrer_;
  std::string user_agent_;
  std::string cookies_;
  std::string media_layer_id_;
  bool video_ = false;
  bool audio_disabled_ = false;

  State state_ = State::kIdle;
  std::string media_id_;
  // Bumped on every load/unload, so replies and events of an old pipeline are dropped.
  int generation_ = 0;
  bool released_ = false;  // unloaded by Suspend(); Resume() reloads at current_time_
  bool metadata_sent_ = false;
  bool load_completed_ = false;
  bool load_complete_signalled_ = false;
  bool ended_ = false;
  bool seeking_ = false;
  media::PipelineStatusCB seek_cb_;

  float playback_rate_ = 0.0f;
  bool playing_reported_ = false;
  double volume_ = 1.0;
  double duration_ = 0.0;
  double current_time_ = 0.0;
  double start_time_ = 0.0;
  double buffer_end_ = 0.0;
  double buffer_end_reported_ = 0.0;
  bool has_audio_ = false;
  bool has_video_ = false;
  gfx::Size natural_video_size_;

  base::Process subscribe_process_;

  base::WeakPtrFactory<WebOSMediaClientLuna> weak_factory_{this};
};

}  // namespace media

#endif  // MEDIA_NEVA_WEBOS_WEBOS_MEDIACLIENT_LUNA_H_
