#include "media/neva/webos/webos_mediaclient_luna.h"

#include <unistd.h>

#include "base/command_line.h"
#include "base/files/file_util.h"
#include "base/files/scoped_file.h"
#include "base/functional/bind.h"
#include "base/json/json_reader.h"
#include "base/json/json_writer.h"
#include "base/logging.h"
#include "base/process/launch.h"
#include "base/strings/string_util.h"
#include "base/task/thread_pool.h"
#include "base/threading/scoped_blocking_call.h"

namespace media {

namespace {

constexpr char kLunaSend[] = "/usr/bin/luna-send";
constexpr char kMediaService[] = "luna://com.webos.media/";
// ozone/wayland/window.cc names the first window "com.webos.app.1"; uMediaServer hands decoders
// only to the foreground app, which on the C1 is that window's appId.
constexpr char kDefaultAppId[] = "com.webos.app.1";
constexpr char kAppIdSwitch[] = "neva-media-app-id";

// One luna-send call, blocking: returns the reply payload ("" on failure).
std::string LunaCall(const std::string& uri, const std::string& payload) {
  base::ScopedBlockingCall blocking(FROM_HERE, base::BlockingType::MAY_BLOCK);
  base::CommandLine cmd({kLunaSend, "-n", "1", uri, payload});
  std::string out;
  if (!base::GetAppOutput(cmd, &out)) {
    LOG(ERROR) << "luna-send failed: " << uri << " " << payload;
    return std::string();
  }
  VLOG(1) << "luna " << uri << " " << payload << " -> " << out.substr(0, 200);
  return out;
}

// Reads `luna-send -i` stdout line by line until EOF and posts each line to |on_line|.
void ReadLines(int fd,
               scoped_refptr<base::SingleThreadTaskRunner> task_runner,
               base::RepeatingCallback<void(const std::string&)> on_line) {
  // Runs on a pool worker for the whole playback. WILL_BLOCK lets the pool add a replacement worker.
  base::ScopedBlockingCall blocking(FROM_HERE, base::BlockingType::WILL_BLOCK);
  base::ScopedFD owned(fd);
  std::string buf;
  char chunk[4096];
  for (;;) {
    ssize_t n = HANDLE_EINTR(read(fd, chunk, sizeof(chunk)));
    if (n <= 0)
      break;
    buf.append(chunk, n);
    size_t pos;
    while ((pos = buf.find('\n')) != std::string::npos) {
      std::string line = buf.substr(0, pos);
      buf.erase(0, pos + 1);
      if (!base::TrimWhitespaceASCII(line, base::TRIM_ALL).empty())
        task_runner->PostTask(FROM_HERE, base::BindOnce(on_line, line));
    }
  }
}

std::string ToJson(const base::Value::Dict& dict) {
  std::string out;
  base::JSONWriter::Write(dict, &out);
  return out;
}

}  // namespace

// static
std::unique_ptr<WebOSMediaClient> WebOSMediaClient::Create(
    const scoped_refptr<base::SingleThreadTaskRunner>& main_task_runner,
    base::WeakPtr<WebOSMediaClient::EventListener> event_listener,
    const std::string& app_id) {
  return std::make_unique<WebOSMediaClientLuna>(main_task_runner,
                                                std::move(event_listener), app_id);
}

WebOSMediaClientLuna::WebOSMediaClientLuna(
    const scoped_refptr<base::SingleThreadTaskRunner>& main_task_runner,
    base::WeakPtr<WebOSMediaClient::EventListener> event_listener,
    const std::string& app_id)
    : main_task_runner_(main_task_runner),
      event_listener_(std::move(event_listener)),
      app_id_(app_id) {
  const auto* cl = base::CommandLine::ForCurrentProcess();
  if (cl->HasSwitch(kAppIdSwitch))
    app_id_ = cl->GetSwitchValueASCII(kAppIdSwitch);
  if (app_id_.empty())
    app_id_ = kDefaultAppId;
}

WebOSMediaClientLuna::~WebOSMediaClientLuna() {
  Unload();
  StopSubscription();
}

void WebOSMediaClientLuna::Load(bool video,
                                double current_time,
                                bool is_local_source,
                                const std::string& url,
                                const std::string& mime_type,
                                const std::string& referrer,
                                const std::string& user_agent,
                                const std::string& cookies,
                                const std::string& payload) {
  video_ = video;
  start_time_ = current_time_ = current_time;
  url_ = url;
  referrer_ = referrer;
  user_agent_ = user_agent;
  cookies_ = cookies;
  LoadNow();
}

std::string WebOSMediaClientLuna::BuildLoadPayload() const {
  base::Value::Dict header;
  header.Set("referer", referrer_);
  header.Set("userAgent", user_agent_);
  header.Set("cookies", cookies_);
  base::Value::Dict transmission;
  transmission.Set("httpHeader", std::move(header));
  if (start_time_ > 0) {
    base::Value::Dict play_time;
    play_time.Set("start", static_cast<double>(static_cast<int64_t>(start_time_ * 1000)));
    transmission.Set("playTime", std::move(play_time));
  }
  base::Value::Dict option;
  option.Set("appId", app_id_);
  if (!media_layer_id_.empty())
    option.Set("windowId", media_layer_id_);
  option.Set("transmission", std::move(transmission));
  option.Set("needAudio", !audio_disabled_);
  option.Set("preload", "false");
  base::Value::Dict media_payload;
  media_payload.Set("option", std::move(option));

  base::Value::Dict load;
  load.Set("uri", url_);
  load.Set("type", "media");
  load.Set("payload", std::move(media_payload));
  return ToJson(load);
}

void WebOSMediaClientLuna::LoadNow() {
  state_ = State::kLoading;
  released_ = false;
  load_completed_ = false;
  metadata_sent_ = false;
  load_complete_signalled_ = false;
  playing_reported_ = false;
  ended_ = false;
  ++generation_;
  base::ThreadPool::PostTaskAndReplyWithResult(
      FROM_HERE, {base::MayBlock()},
      base::BindOnce(&LunaCall, std::string(kMediaService) + "load", BuildLoadPayload()),
      base::BindOnce(
          [](base::WeakPtr<WebOSMediaClientLuna> self, int generation,
             const std::string& reply) {
            if (self && self->generation_ == generation)
              self->OnLoaded(reply);
          },
          weak_factory_.GetWeakPtr(), generation_));
}

void WebOSMediaClientLuna::OnLoaded(const std::string& reply) {
  absl::optional<base::Value> v = base::JSONReader::Read(reply);
  const std::string* id =
      v && v->is_dict() ? v->GetDict().FindString("mediaId") : nullptr;
  if (!id || id->empty()) {
    LOG(ERROR) << "com.webos.media/load failed: " << reply;
    state_ = State::kIdle;
    if (event_listener_)
      event_listener_->OnError(PIPELINE_ERROR_INITIALIZATION_FAILED);
    return;
  }
  media_id_ = *id;

  // Event stream for this pipeline.
  int fds[2];
  if (pipe(fds) == 0) {
    base::LaunchOptions options;
    options.fds_to_remap.emplace_back(fds[1], STDOUT_FILENO);
    base::Value::Dict sub;
    sub.Set("mediaId", media_id_);
    subscribe_process_ = base::LaunchProcess(
        base::CommandLine(
            {kLunaSend, "-i", std::string(kMediaService) + "subscribe", ToJson(sub)}),
        options);
    close(fds[1]);
    int generation = generation_;
    base::ThreadPool::PostTask(
        FROM_HERE, {base::MayBlock()},
        base::BindOnce(&ReadLines, fds[0], main_task_runner_,
                       base::BindRepeating(
                           [](base::WeakPtr<WebOSMediaClientLuna> self, int generation,
                              const std::string& line) {
                             if (self && self->generation_ == generation)
                               self->OnEvent(line);
                           },
                           weak_factory_.GetWeakPtr(), generation)));
  }

  base::Value::Dict params;
  Call("notifyForeground", std::move(params));
  SetPlaybackVolume(volume_, true);
  if (playback_rate_ != 0.0f)
    Call("play", base::Value::Dict());
}

void WebOSMediaClientLuna::Call(const std::string& method, base::Value::Dict params) {
  if (media_id_.empty())
    return;
  params.Set("mediaId", media_id_);
  base::ThreadPool::PostTask(
      FROM_HERE, {base::MayBlock()},
      base::BindOnce(base::IgnoreResult(&LunaCall), std::string(kMediaService) + method,
                     ToJson(params)));
}

void WebOSMediaClientLuna::StopSubscription() {
  if (!subscribe_process_.IsValid())
    return;
  // Killing luna-send closes the pipe, so ReadLines sees EOF and its worker returns.
  // The kill and the reap run on the pool: the main thread may not wait.
  base::ThreadPool::PostTask(
      FROM_HERE, {base::MayBlock(), base::WithBaseSyncPrimitives()},
      base::BindOnce([](base::Process p) { p.Terminate(0, /*wait=*/true); },
                     std::move(subscribe_process_)));
  subscribe_process_ = base::Process();
}

void WebOSMediaClientLuna::Seek(base::TimeDelta time,
                                const media::PipelineStatusCB& seek_cb) {
  ended_ = false;
  current_time_ = time.InSecondsF();
  seek_cb_ = seek_cb;
  seeking_ = true;
  base::Value::Dict params;
  params.Set("position", static_cast<double>(time.InMilliseconds()));
  Call("seek", std::move(params));
}

void WebOSMediaClientLuna::SetPlaybackRate(float playback_rate) {
  float old = playback_rate_;
  playback_rate_ = playback_rate;
  if (media_id_.empty() || state_ == State::kIdle)
    return;  // applied after load
  if (playback_rate == 0.0f) {
    Call("pause", base::Value::Dict());
    return;
  }
  if (playback_rate != 1.0f || (old != 0.0f && old != playback_rate)) {
    base::Value::Dict params;
    params.Set("playRate", playback_rate);
    params.Set("audioOutput", playback_rate == 1.0f);
    Call("setPlayRate", std::move(params));
  }
  if (old == 0.0f) {
    ended_ = false;
    Call("play", base::Value::Dict());
  }
}

void WebOSMediaClientLuna::SetPlaybackVolume(double volume, bool forced) {
  if (volume_ == volume && !forced)
    return;
  volume_ = volume;
  base::Value::Dict params;
  params.Set("volume", static_cast<int>(volume * 100));
  Call("setVolume", std::move(params));
}

void WebOSMediaClientLuna::Suspend(SuspendReason reason) {
  if (media_id_.empty())
    return;
  Unload();
  released_ = true;
}

void WebOSMediaClientLuna::Resume() {
  if (!released_)
    return;
  start_time_ = current_time_;
  LoadNow();
}

media::Ranges<base::TimeDelta> WebOSMediaClientLuna::GetBufferedTimeRanges() const {
  media::Ranges<base::TimeDelta> ranges;
  ranges.Add(base::TimeDelta(), base::Seconds(buffer_end_));
  return ranges;
}

bool WebOSMediaClientLuna::DidLoadingProgress() {
  bool progress = buffer_end_ != buffer_end_reported_;
  buffer_end_reported_ = buffer_end_;
  return progress;
}

void WebOSMediaClientLuna::Unload() {
  ++generation_;
  if (!media_id_.empty()) {
    base::Value::Dict params;
    params.Set("mediaId", media_id_);
    base::ThreadPool::PostTask(
        FROM_HERE, {base::MayBlock()},
        base::BindOnce(base::IgnoreResult(&LunaCall),
                       std::string(kMediaService) + "unload", ToJson(params)));
  }
  media_id_.clear();
  state_ = State::kIdle;
  StopSubscription();
}

void WebOSMediaClientLuna::SignalLoadCompleted() {
  if (load_complete_signalled_ || !load_completed_ || !metadata_sent_ || !event_listener_)
    return;
  load_complete_signalled_ = true;
  event_listener_->OnBufferingStatusChanged(BufferingState::kLoadCompleted);
}

void WebOSMediaClientLuna::HandleVideoSize(int width, int height) {
  if (width <= 0 || height <= 0)
    return;
  has_video_ = true;
  gfx::Size size(width, height);
  if (size == natural_video_size_)
    return;
  natural_video_size_ = size;
  if (event_listener_)
    event_listener_->OnVideoSizeChanged();
}

void WebOSMediaClientLuna::HandleSourceInfo(const base::Value::Dict& info) {
  const base::Value::List* programs = info.FindList("programInfo");
  if (programs && !programs->empty() && (*programs)[0].is_dict()) {
    const base::Value::Dict& p = (*programs)[0].GetDict();
    if (absl::optional<double> d = p.FindDouble("duration"); d && *d > 0) {
      double seconds = *d / 1000.0;
      if (seconds != duration_) {
        duration_ = seconds;
        if (event_listener_)
          event_listener_->OnDurationChanged();
      }
    }
    has_video_ = p.FindInt("numVideoTracks").value_or(video_ ? 1 : 0) > 0;
    has_audio_ = p.FindInt("numAudioTracks").value_or(0) > 0;
    if (const base::Value::List* tracks = p.FindList("videoTrackInfo");
        tracks && !tracks->empty() && (*tracks)[0].is_dict()) {
      const base::Value::Dict& t = (*tracks)[0].GetDict();
      HandleVideoSize(t.FindInt("width").value_or(0), t.FindInt("height").value_or(0));
    }
  }
  if (event_listener_) {
    metadata_sent_ = true;
    event_listener_->OnBufferingStatusChanged(BufferingState::kHaveMetadata);
  }
  SignalLoadCompleted();
}

void WebOSMediaClientLuna::HandleError(int code, const std::string& text) {
  LOG(ERROR) << "com.webos.media error " << code << " " << text;
  PipelineStatus status = PIPELINE_OK;
  if (code >= 100 && code < 200 && code != 101)
    status = PIPELINE_ERROR_INITIALIZATION_FAILED;
  else if (code >= 200 && code < 300)
    status = (code == 200 && !has_audio_) || (code == 201 && !has_video_) || code == 210
                 ? PIPELINE_OK
                 : PIPELINE_ERROR_ABORT;
  else if (code >= 300 && code < 500)
    status = PIPELINE_ERROR_NETWORK;
  else if (code >= 500 && code < 600)
    status = PIPELINE_ERROR_DECRYPT;
  else if (code >= 600 && code < 700)
    status = PIPELINE_ERROR_ABORT;
  else if (code >= 700 && code < 800) {
    if (seeking_) {
      seeking_ = false;
      if (seek_cb_)
        std::move(seek_cb_).Run(PIPELINE_OK);
    }
  } else if (code >= 1000)
    status = PIPELINE_ERROR_ABORT;
  if (status != PIPELINE_OK && event_listener_)
    event_listener_->OnError(status);
}

void WebOSMediaClientLuna::OnEvent(const std::string& line) {
  VLOG(2) << "ums event " << line.substr(0, 200);
  absl::optional<base::Value> v = base::JSONReader::Read(line);
  if (!v || !v->is_dict())
    return;
  const base::Value::Dict& ev = v->GetDict();

  if (const base::Value::Dict* t = ev.FindDict("currentTime")) {
    if (ended_ || seeking_)
      return;
    double ms = t->FindDouble("currentTime").value_or(0);
    current_time_ = ms / 1000.0;
    if (event_listener_)
      event_listener_->OnTimeUpdated(base::Milliseconds(ms));
  } else if (const base::Value::Dict* b = ev.FindDict("bufferRange")) {
    buffer_end_ = b->FindDouble("endTime").value_or(0);
    if (duration_ > 0 && (b->FindDouble("remainingTime").value_or(0) == -1 ||
                          buffer_end_ > duration_))
      buffer_end_ = duration_;
  } else if (ev.Find("loadCompleted")) {
    state_ = State::kLoaded;
    load_completed_ = true;
    SignalLoadCompleted();
  } else if (const base::Value::Dict* s = ev.FindDict("sourceInfo")) {
    HandleSourceInfo(*s);
  } else if (const base::Value::Dict* vi = ev.FindDict("videoInfo")) {
    HandleVideoSize(vi->FindInt("width").value_or(0), vi->FindInt("height").value_or(0));
  } else if (ev.Find("audioInfo")) {
    has_audio_ = true;
  } else if (ev.Find("playing")) {
    ended_ = false;
    if (event_listener_)
      event_listener_->OnPlaybackStateChanged(true);
  } else if (ev.Find("paused")) {
    if (event_listener_)
      event_listener_->OnPlaybackStateChanged(false);
  } else if (ev.Find("seekDone")) {
    if (seeking_) {
      seeking_ = false;
      if (seek_cb_)
        std::move(seek_cb_).Run(PIPELINE_OK);
    }
  } else if (ev.Find("endOfStream")) {
    ended_ = true;
    if (duration_ > 0)
      current_time_ = duration_;
    if (event_listener_)
      event_listener_->OnPlaybackEnded();
  } else if (ev.Find("bufferingStart")) {
    if (event_listener_)
      event_listener_->OnBufferingStatusChanged(BufferingState::kWebOSBufferingStart);
  } else if (ev.Find("bufferingEnd")) {
    if (event_listener_)
      event_listener_->OnBufferingStatusChanged(BufferingState::kWebOSBufferingEnd);
  } else if (const base::Value::Dict* e = ev.FindDict("error")) {
    HandleError(e->FindInt("errorCode").value_or(0),
                e->FindString("errorText") ? *e->FindString("errorText") : std::string());
  }
}

}  // namespace media
