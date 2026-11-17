// From WebOS-Chromium (github.com/sarahahzub/WebOS-Chromium, BSD-3), patch 0023, adapted to Chromium 120.
//
// CnNdlRenderer plays a <video> on LG's hardware decoder. It reads demuxed video packets (Annex B for H.264/HEVC,
// raw frames for VP9/AV1), decodes audio itself with FFmpeg to S16 stereo PCM (NDL takes PCM; AAC/MP3/Vorbis/Opus
// all work that way), and sends both over $CN_MEDIA_SOCK to the launcher with a small lead. The picture is drawn by
// the TV on its video plane; Chrome only shows a VideoHole frame, which viz turns into a transparent hole and whose
// position it reports to the launcher (patch 0023, skia_renderer.cc).
// Streams it cannot take (other codecs, encrypted, audio-only, odd sample rates, no launcher) go to RendererImpl.

#include "content/renderer/media/cn_ndl_renderer.h"

#include <sys/socket.h>
#include <sys/uio.h>
#include <sys/un.h>
#include <unistd.h>

#include <cerrno>
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <vector>

#include "base/functional/bind.h"
#include "base/functional/callback_helpers.h"
#include "base/logging.h"
#include "base/memory/weak_ptr.h"
#include "base/task/sequenced_task_runner.h"
#include "base/time/time.h"
#include "base/unguessable_token.h"
#include "media/base/audio_buffer.h"
#include "media/base/audio_bus.h"
#include "media/base/audio_decoder_config.h"
#include "media/base/decoder_buffer.h"
#include "media/base/demuxer_stream.h"
#include "media/base/media_resource.h"
#include "media/base/pipeline_status.h"
#include "media/base/renderer.h"
#include "media/base/renderer_client.h"
#include "media/base/video_codecs.h"
#include "media/base/video_decoder_config.h"
#include "media/base/video_frame.h"
#include "media/base/video_renderer_sink.h"
#include "media/filters/ffmpeg_audio_decoder.h"

namespace content {
namespace {

enum : uint32_t { kOpen = 1, kVideo = 2, kAudio = 3, kClose = 4, kSrc = 6 };
struct Open { uint64_t token[2]; int32_t codec, width, height, audio_rate, audio_channels; };
struct Src { uint64_t token[2]; int32_t w, h; };

int NdlCodec(media::VideoCodec c) {
  switch (c) {
    case media::VideoCodec::kH264: return 1;
    case media::VideoCodec::kHEVC: return 2;
    case media::VideoCodec::kVP9: return 3;
    case media::VideoCodec::kAV1: return 4;
    default: return 0;
  }
}
bool NdlRate(int hz) {
  return hz == 48000 || hz == 44100 || hz == 32000 || hz == 24000 || hz == 16000 || hz == 12000 || hz == 8000 ||
         hz == 22050;
}
int EnvInt(const char* name, int def) {
  const char* v = getenv(name);
  return v && *v ? atoi(v) : def;
}

class CnNdlRenderer : public media::Renderer {
 public:
  CnNdlRenderer(std::unique_ptr<media::Renderer> fallback,
                scoped_refptr<base::SequencedTaskRunner> task_runner,
                media::VideoRendererSink* sink,
                media::MediaLog* media_log)
      : fallback_(std::move(fallback)), task_runner_(std::move(task_runner)), sink_(sink), media_log_(media_log),
        token_(base::UnguessableToken::Create()), lead_(base::Milliseconds(EnvInt("CN_NDL_LEAD_MS", 150))) {}

  ~CnNdlRenderer() override {
    if (fd_ >= 0) {
      SendClose();
      close(fd_);
    }
  }

  void Initialize(media::MediaResource* resource, media::RendererClient* client,
                  media::PipelineStatusCallback init_cb) override {
    resource_ = resource;
    client_ = client;
    video_ = resource->GetFirstStream(media::DemuxerStream::VIDEO);
    audio_ = resource->GetFirstStream(media::DemuxerStream::AUDIO);
    if (!Suitable() || !Connect()) {
      LOG(WARNING) << "cn-ndl: software playback ("
                   << (!video_ ? std::string("no video")
                               : media::GetCodecName(video_->video_decoder_config().codec()) +
                                     (video_->video_decoder_config().is_encrypted() ? " encrypted" : "") +
                                     (Suitable() ? ", launcher socket unreachable" : ", unsuitable"))
                   << ")";
      UseFallback(std::move(init_cb));
      return;
    }
    vcfg_ = video_->video_decoder_config();
    video_->EnableBitstreamConverter();  // FFmpegDemuxer H.264/HEVC -> Annex B; MSE already is
    LOG(WARNING) << "cn-ndl: hardware video " << media::GetCodecName(vcfg_.codec()) << " "
                 << vcfg_.natural_size().ToString() << (audio_ ? " + audio" : "");
    if (audio_) {
      // Chromium 120's FFmpegAudioDecoder also decodes Opus (YouTube's audio); 151 needed OpusAudioDecoder.
      audio_decoder_ = std::make_unique<media::FFmpegAudioDecoder>(task_runner_, media_log_);
      audio_decoder_->Initialize(
          audio_->audio_decoder_config(), nullptr,
          base::BindOnce(&CnNdlRenderer::OnAudioDecoderInit, weak_.GetWeakPtr(), std::move(init_cb)),
          base::BindRepeating(&CnNdlRenderer::OnAudioOutput, weak_.GetWeakPtr()), base::DoNothing());
      return;
    }
    FinishInit(std::move(init_cb));
  }

  void SetCdm(media::CdmContext* cdm, CdmAttachedCB cb) override {
    if (fallback_mode_) {
      fallback_->SetCdm(cdm, std::move(cb));
      return;
    }
    std::move(cb).Run(false);
  }
  void SetLatencyHint(absl::optional<base::TimeDelta> hint) override {
    if (fallback_mode_) fallback_->SetLatencyHint(hint);
  }
  void SetPreservesPitch(bool v) override {
    if (fallback_mode_) fallback_->SetPreservesPitch(v);
  }
  void SetWasPlayedWithUserActivation(bool v) override {
    if (fallback_mode_) fallback_->SetWasPlayedWithUserActivation(v);
  }

  void Flush(base::OnceClosure cb) override {
    if (fallback_mode_) {
      fallback_->Flush(std::move(cb));
      return;
    }
    LOG(WARNING) << "cn-ndl: flush";
    ++gen_;
    started_ = false;
    pending_video_.reset();
    audio_queue_.clear();
    video_eos_ = audio_eos_ = ended_ = false;
    sent_first_video_ = false;
    SendClose();
    if (have_enough_) {
      have_enough_ = false;
      client_->OnBufferingStateChange(media::BUFFERING_HAVE_NOTHING, media::BUFFERING_CHANGE_REASON_UNKNOWN);
    }
    if (audio_decoder_) {
      accept_audio_ = false;
      audio_decoder_->Reset(base::BindOnce(&CnNdlRenderer::OnAudioReset, weak_.GetWeakPtr(), std::move(cb)));
      return;
    }
    task_runner_->PostTask(FROM_HERE, std::move(cb));
  }

  void StartPlayingFrom(base::TimeDelta t) override {
    if (fallback_mode_) {
      fallback_->StartPlayingFrom(t);
      return;
    }
    LOG(WARNING) << "cn-ndl: start at " << t.InMillisecondsF() << " ms";
    started_ = true;
    accept_audio_ = true;
    base_media_ = last_media_ = t;
    base_wall_ = open_wall_ = base::TimeTicks::Now();
    last_video_ts_ = last_audio_end_ = t;
    SendOpen();
    RequestVideo();
    Pump();
    if (!ticking_) {
      ticking_ = true;
      task_runner_->PostDelayedTask(FROM_HERE, base::BindOnce(&CnNdlRenderer::Tick, weak_.GetWeakPtr()),
                                    base::Milliseconds(10));
    }
  }

  void SetPlaybackRate(double rate) override {
    if (fallback_mode_) {
      fallback_->SetPlaybackRate(rate);
      return;
    }
    base_media_ = MediaTime();
    base_wall_ = base::TimeTicks::Now();
    playing_ = rate > 0;
  }

  void SetVolume(float volume) override {
    if (fallback_mode_) {
      fallback_->SetVolume(volume);
      return;
    }
    volume_ = volume;
  }

  base::TimeDelta GetMediaTime() override { return fallback_mode_ ? fallback_->GetMediaTime() : MediaTime(); }

  void OnSelectedVideoTracksChanged(const std::vector<media::DemuxerStream*>& tracks,
                                    base::OnceClosure done) override {
    if (fallback_mode_) {
      fallback_->OnSelectedVideoTracksChanged(tracks, std::move(done));
      return;
    }
    std::move(done).Run();
  }
  void OnEnabledAudioTracksChanged(const std::vector<media::DemuxerStream*>& tracks,
                                   base::OnceClosure done) override {
    if (fallback_mode_) {
      fallback_->OnEnabledAudioTracksChanged(tracks, std::move(done));
      return;
    }
    std::move(done).Run();
  }

  media::RendererType GetRendererType() override {
    return fallback_mode_ ? fallback_->GetRendererType() : media::RendererType::kContentEmbedderDefined;
  }

 private:
  bool Suitable() {
    if (!video_) return false;  // audio only: software is cheap
    const auto vc = video_->video_decoder_config();
    if (!NdlCodec(vc.codec()) || vc.is_encrypted()) return false;
    if (audio_) {
      const auto ac = audio_->audio_decoder_config();
      if (ac.is_encrypted() || !NdlRate(ac.samples_per_second())) return false;
    }
    return true;
  }

  bool Connect() {
    const char* path = getenv("CN_MEDIA_SOCK");
    if (!path || !*path) return false;
    int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0) return false;
    sockaddr_un a{};
    a.sun_family = AF_UNIX;
    strncpy(a.sun_path, path, sizeof(a.sun_path) - 1);
    if (connect(fd, reinterpret_cast<sockaddr*>(&a), sizeof(a)) != 0) {
      PLOG(WARNING) << "cn-ndl: connect " << path;
      close(fd);
      return false;
    }
    int sz = 4 << 20;
    setsockopt(fd, SOL_SOCKET, SO_SNDBUF, &sz, sizeof(sz));
    fd_ = fd;
    return true;
  }

  void UseFallback(media::PipelineStatusCallback init_cb) {
    fallback_mode_ = true;
    if (fd_ >= 0) {
      close(fd_);
      fd_ = -1;
    }
    audio_decoder_.reset();
    fallback_->Initialize(resource_, client_, std::move(init_cb));
  }

  void OnAudioDecoderInit(media::PipelineStatusCallback init_cb, media::DecoderStatus status) {
    if (!status.is_ok()) {
      LOG(WARNING) << "cn-ndl: audio decoder init failed, software playback";
      UseFallback(std::move(init_cb));
      return;
    }
    FinishInit(std::move(init_cb));
  }

  void FinishInit(media::PipelineStatusCallback init_cb) {
    natural_size_ = vcfg_.natural_size();
    client_->OnVideoNaturalSizeChange(natural_size_);
    client_->OnVideoOpacityChange(true);
    PaintHole();
    std::move(init_cb).Run(media::PIPELINE_OK);
  }

  void PaintHole() {
    sink_->PaintSingleFrame(media::VideoFrame::CreateVideoHoleFrame(token_, natural_size_, base::TimeDelta()), true);
  }

  // Media clock: wall clock while playing, held when paused; never runs more than 300 ms past the data we sent
  // (stall while the demuxer starves, so the page shows buffering instead of skipping).
  base::TimeDelta MediaTime() {
    base::TimeDelta t = base_media_;
    if (playing_ && started_) t += base::TimeTicks::Now() - base_wall_;
    if (started_ && !video_eos_) t = std::min(t, last_video_ts_ + base::Milliseconds(300));
    t = std::max(t, last_media_);
    last_media_ = t;
    return t;
  }

  int64_t PtsMs(base::TimeDelta ts) {
    base::TimeDelta p = (base::TimeTicks::Now() - open_wall_) + (ts - MediaTime());
    return std::max<int64_t>(0, p.InMilliseconds());
  }

  bool Send(uint32_t type, const void* a, size_t alen, const void* b, size_t blen) {
    if (fd_ < 0) return false;
    uint32_t hdr[2] = {type, static_cast<uint32_t>(alen + blen)};
    iovec iov[3] = {{hdr, sizeof(hdr)}, {const_cast<void*>(a), alen}, {const_cast<void*>(b), blen}};
    size_t total = sizeof(hdr) + alen + blen;
    msghdr m{};
    m.msg_iov = iov;
    m.msg_iovlen = 3;
    while (total > 0) {
      ssize_t r = sendmsg(fd_, &m, MSG_NOSIGNAL);
      if (r < 0) {
        if (errno == EINTR) continue;
        PLOG(ERROR) << "cn-ndl: launcher socket";
        close(fd_);
        fd_ = -1;
        LOG(ERROR) << "cn-ndl: pipeline error DECODE at line " << __LINE__; client_->OnError(media::PIPELINE_ERROR_DECODE);
        return false;
      }
      total -= r;
      while (r > 0 && m.msg_iovlen > 0) {  // advance over what was sent
        size_t n = std::min<size_t>(r, m.msg_iov[0].iov_len);
        m.msg_iov[0].iov_base = static_cast<char*>(m.msg_iov[0].iov_base) + n;
        m.msg_iov[0].iov_len -= n;
        r -= n;
        if (m.msg_iov[0].iov_len == 0) {
          m.msg_iov++;
          m.msg_iovlen--;
        }
      }
    }
    return true;
  }

  void Token(uint64_t out[2]) {
    out[0] = token_.GetHighForSerialization();
    out[1] = token_.GetLowForSerialization();
  }

  void SendOpen() {
    Open o{};
    Token(o.token);
    o.codec = NdlCodec(vcfg_.codec());
    o.width = natural_size_.width();
    o.height = natural_size_.height();
    o.audio_rate = audio_ ? audio_->audio_decoder_config().samples_per_second() : 0;
    o.audio_channels = 2;
    Send(kOpen, &o, sizeof(o), nullptr, 0);
  }
  void SendClose() {
    uint64_t t[2];
    Token(t);
    Send(kClose, t, sizeof(t), nullptr, 0);
  }

  void RequestVideo() {
    if (video_read_pending_ || video_eos_ || pending_video_ || !started_) return;
    video_read_pending_ = true;
    video_->Read(1, base::BindOnce(&CnNdlRenderer::OnVideoRead, weak_.GetWeakPtr(), gen_));
  }

  void OnVideoRead(int gen, media::DemuxerStream::Status status, media::DemuxerStream::DecoderBufferVector bufs) {
    video_read_pending_ = false;
    if (gen != gen_ || !started_) {
      RequestVideo();
      return;
    }
    switch (status) {
      case media::DemuxerStream::kOk:
        if (bufs.empty()) break;
        if (bufs[0]->end_of_stream()) {
          video_eos_ = true;
        } else {
          pending_video_ = std::move(bufs[0]);
        }
        break;
      case media::DemuxerStream::kConfigChanged: {
        auto c = video_->video_decoder_config();
        if (NdlCodec(c.codec()) != NdlCodec(vcfg_.codec())) {
          vcfg_ = c;
          natural_size_ = c.natural_size();
          SendOpen();  // codec switch needs a new NDL stream
        } else if (c.natural_size() != natural_size_) {
          natural_size_ = c.natural_size();
          Src s{};
          Token(s.token);
          s.w = natural_size_.width();
          s.h = natural_size_.height();
          Send(kSrc, &s, sizeof(s), nullptr, 0);
        }
        vcfg_ = c;
        client_->OnVideoNaturalSizeChange(natural_size_);
        PaintHole();
        RequestVideo();
        return;
      }
      case media::DemuxerStream::kAborted:
        return;
      case media::DemuxerStream::kError:
        LOG(ERROR) << "cn-ndl: pipeline error READ at line " << __LINE__; client_->OnError(media::PIPELINE_ERROR_READ);
        return;
    }
    Pump();
  }

  void RequestAudio() {
    if (!audio_ || audio_read_pending_ || audio_decode_pending_ || audio_eos_ || !started_) return;
    base::TimeDelta queued = audio_queue_.empty() ? base::TimeDelta()
                                                  : audio_queue_.back()->timestamp() - audio_queue_.front()->timestamp();
    if (queued > base::Seconds(1)) return;
    audio_read_pending_ = true;
    audio_->Read(1, base::BindOnce(&CnNdlRenderer::OnAudioRead, weak_.GetWeakPtr(), gen_));
  }

  void OnAudioRead(int gen, media::DemuxerStream::Status status, media::DemuxerStream::DecoderBufferVector bufs) {
    audio_read_pending_ = false;
    if (gen != gen_ || !started_) return;
    if (status == media::DemuxerStream::kConfigChanged) {
      // New audio format mid-stream: re-init the decoder; keep going.
      audio_decode_pending_ = true;
      audio_decoder_->Initialize(audio_->audio_decoder_config(), nullptr,
                                 base::BindOnce(&CnNdlRenderer::OnAudioReinit, weak_.GetWeakPtr(), gen),
                                 base::BindRepeating(&CnNdlRenderer::OnAudioOutput, weak_.GetWeakPtr()),
                                 base::DoNothing());
      return;
    }
    if (status == media::DemuxerStream::kError) {
      LOG(ERROR) << "cn-ndl: pipeline error READ at line " << __LINE__; client_->OnError(media::PIPELINE_ERROR_READ);
      return;
    }
    if (status != media::DemuxerStream::kOk || bufs.empty()) return;
    audio_decode_pending_ = true;
    bool eos = bufs[0]->end_of_stream();
    audio_decoder_->Decode(std::move(bufs[0]),
                           base::BindOnce(&CnNdlRenderer::OnAudioDecoded, weak_.GetWeakPtr(), gen, eos));
  }

  void OnAudioReinit(int gen, media::DecoderStatus status) {
    audio_decode_pending_ = false;
    if (!status.is_ok()) LOG(ERROR) << "cn-ndl: pipeline error DECODE at line " << __LINE__; client_->OnError(media::PIPELINE_ERROR_DECODE);
    if (gen == gen_) Pump();
  }

  void OnAudioDecoded(int gen, bool eos, media::DecoderStatus status) {
    audio_decode_pending_ = false;
    if (gen != gen_) return;
    if (!status.is_ok()) {
      LOG(ERROR) << "cn-ndl: pipeline error DECODE at line " << __LINE__; client_->OnError(media::PIPELINE_ERROR_DECODE);
      return;
    }
    if (eos) audio_eos_ = true;
    Pump();
  }

  void OnAudioOutput(scoped_refptr<media::AudioBuffer> buf) {
    if (accept_audio_ && started_) audio_queue_.push_back(std::move(buf));
  }

  void OnAudioReset(base::OnceClosure cb) { std::move(cb).Run(); }

  void SendAudio(const media::AudioBuffer& b) {
    const int frames = b.frame_count(), ch = b.channel_count();
    if (frames <= 0 || ch <= 0) return;
    auto bus = media::AudioBus::Create(ch, frames);
    b.ReadFrames(frames, 0, 0, bus.get());
    pcm_.resize(frames * 2);
    const float v = volume_;
    for (int i = 0; i < frames; i++) {
      float l = bus->channel(0)[i], r = ch > 1 ? bus->channel(1)[i] : l;
      if (ch > 2) {  // simple downmix: centre (and the rest) at -3 dB
        float c = 0;
        for (int k = 2; k < ch; k++) c += bus->channel(k)[i];
        l += 0.707f * c / (ch - 2);
        r += 0.707f * c / (ch - 2);
      }
      pcm_[2 * i] = static_cast<int16_t>(std::clamp(l * v, -1.f, 1.f) * 32767.f);
      pcm_[2 * i + 1] = static_cast<int16_t>(std::clamp(r * v, -1.f, 1.f) * 32767.f);
    }
    int64_t pts = PtsMs(b.timestamp());
    Send(kAudio, &pts, sizeof(pts), pcm_.data(), pcm_.size() * sizeof(int16_t));
    last_audio_end_ = b.timestamp() + b.duration();
  }

  void SendVideo(const media::DecoderBuffer& b) {
    int64_t pts = PtsMs(b.timestamp());
    Send(kVideo, &pts, sizeof(pts), b.data(), b.data_size());
    last_video_ts_ = std::max(last_video_ts_, b.timestamp());
    sent_first_video_ = true;
    stats_.video_frames_decoded = 1;
    stats_.video_bytes_decoded = b.data_size();
    client_->OnStatisticsUpdate(stats_);
  }

  // 10 ms timer while playing; stops itself after Flush.
  void Tick() {
    if (!started_ || fallback_mode_) {
      ticking_ = false;
      return;
    }
    Pump();
    task_runner_->PostDelayedTask(FROM_HERE, base::BindOnce(&CnNdlRenderer::Tick, weak_.GetWeakPtr()),
                                  base::Milliseconds(10));
  }

  void Pump() {
    if (!started_ || fallback_mode_) return;
    const base::TimeDelta now = MediaTime();
    if (pending_video_ && (playing_ ? pending_video_->timestamp() - now <= lead_ : !sent_first_video_)) {
      SendVideo(*pending_video_);
      pending_video_.reset();
    }
    while (playing_ && !audio_queue_.empty() && audio_queue_.front()->timestamp() - now <= lead_) {
      SendAudio(*audio_queue_.front());
      audio_queue_.pop_front();
    }
    RequestVideo();
    RequestAudio();
    if (!have_enough_ && (sent_first_video_ || video_eos_) && (!audio_ || !audio_queue_.empty() || audio_eos_)) {
      have_enough_ = true;
      client_->OnBufferingStateChange(media::BUFFERING_HAVE_ENOUGH, media::BUFFERING_CHANGE_REASON_UNKNOWN);
    }
    if (!ended_ && video_eos_ && !pending_video_ && (!audio_ || (audio_eos_ && audio_queue_.empty())) &&
        now >= std::max(last_video_ts_, last_audio_end_)) {
      ended_ = true;
      client_->OnEnded();
    }
  }

  std::unique_ptr<media::Renderer> fallback_;
  scoped_refptr<base::SequencedTaskRunner> task_runner_;
  raw_ptr<media::VideoRendererSink> sink_;
  raw_ptr<media::MediaLog> media_log_;
  raw_ptr<media::MediaResource> resource_ = nullptr;
  raw_ptr<media::RendererClient> client_ = nullptr;
  raw_ptr<media::DemuxerStream> video_ = nullptr;
  raw_ptr<media::DemuxerStream> audio_ = nullptr;
  std::unique_ptr<media::AudioDecoder> audio_decoder_;
  const base::UnguessableToken token_;
  const base::TimeDelta lead_;
  media::VideoDecoderConfig vcfg_;
  gfx::Size natural_size_;
  media::PipelineStatistics stats_;
  int fd_ = -1;
  int gen_ = 0;
  bool fallback_mode_ = false, started_ = false, playing_ = false, have_enough_ = false, ended_ = false;
  bool video_eos_ = false, audio_eos_ = false, sent_first_video_ = false, accept_audio_ = false;
  bool video_read_pending_ = false, audio_read_pending_ = false, audio_decode_pending_ = false;
  bool ticking_ = false;
  float volume_ = 1.f;
  base::TimeDelta base_media_, last_media_, last_video_ts_, last_audio_end_;
  base::TimeTicks base_wall_, open_wall_;
  scoped_refptr<media::DecoderBuffer> pending_video_;
  std::deque<scoped_refptr<media::AudioBuffer>> audio_queue_;
  std::vector<int16_t> pcm_;
  base::WeakPtrFactory<CnNdlRenderer> weak_{this};
};

}  // namespace

CnNdlRendererFactory::CnNdlRendererFactory(std::unique_ptr<media::RendererFactory> fallback,
                                           media::MediaLog* media_log)
    : fallback_(std::move(fallback)), media_log_(media_log) {}
CnNdlRendererFactory::~CnNdlRendererFactory() = default;

// static
bool CnNdlRendererFactory::Enabled() {
  const char* s = getenv("CN_MEDIA_SOCK");
  return s && *s;
}

std::unique_ptr<media::Renderer> CnNdlRendererFactory::CreateRenderer(
    const scoped_refptr<base::SequencedTaskRunner>& media_task_runner,
    const scoped_refptr<base::TaskRunner>& worker_task_runner,
    media::AudioRendererSink* audio_renderer_sink,
    media::VideoRendererSink* video_renderer_sink,
    media::RequestOverlayInfoCB request_overlay_info_cb,
    const gfx::ColorSpace& target_color_space) {
  auto fallback = fallback_->CreateRenderer(media_task_runner, worker_task_runner, audio_renderer_sink,
                                            video_renderer_sink, std::move(request_overlay_info_cb),
                                            target_color_space);
  return std::make_unique<CnNdlRenderer>(std::move(fallback), media_task_runner, video_renderer_sink, media_log_);
}

}  // namespace content
