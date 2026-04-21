import { useEffect, useState, useRef, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, RefreshCw, Download, Copy, Music, Sparkles, RotateCcw } from 'lucide-react';
import { toast } from 'react-toastify';
import api from '../api';
import { StatusPill } from './DashboardPage';

export default function GenerationBatchPage() {
  const { uuid } = useParams();
  const [batch, setBatch] = useState(null);
  const pollRef = useRef(null);

  const refresh = () => api.get(`/api/generations/batches/${uuid}/`).then((r) => setBatch(r.data));
  useEffect(() => { refresh(); }, [uuid]);

  // Re-key on the concatenated status string so the effect re-runs whenever
  // ANY take transitions, not just when the batch's own status changes.
  const allTakeStatuses = batch
    ? batch.generations.map((g) => g.status).join(',')
    : '';

  useEffect(() => {
    if (!batch) return;
    const stillRunning = batch.generations.some((g) => ['pending', 'running'].includes(g.status));
    if (!stillRunning) { if (pollRef.current) clearInterval(pollRef.current); return; }
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(refresh, 3000);
    return () => clearInterval(pollRef.current);
  }, [batch?.status, allTakeStatuses]);

  // Group generations by scenario for display
  const scenarioGroups = useMemo(() => {
    if (!batch) return [];
    const map = new Map();
    batch.generations
      .slice()
      .sort((a, b) => (a.scenario || '').localeCompare(b.scenario || '') || a.take_index - b.take_index)
      .forEach((g) => {
        const key = g.scenario || '(no scenario)';
        if (!map.has(key)) map.set(key, []);
        map.get(key).push(g);
      });
    return Array.from(map.entries()).map(([scenario, takes]) => ({ scenario, takes }));
  }, [batch]);

  if (!batch) return <div>Loading…</div>;

  const regenerate = async (genUuid) => {
    await api.post(`/api/generations/${genUuid}/regenerate/`);
    toast.info('Regenerating…');
    refresh();
  };
  const cancel = async (genUuid) => {
    await api.post(`/api/generations/${genUuid}/cancel/`);
    refresh();
  };

  return (
    <div>
      <Link to="/generations" className="small text-muted text-decoration-none d-inline-flex align-items-center gap-1 mb-3">
        <ArrowLeft size={14} /> All batches
      </Link>

      <div className="d-flex justify-content-between align-items-center mb-4">
        <div>
          <h2 className="mb-1">{batch.subject_name} · {batch.theme_name}</h2>
          <p className="text-muted mb-0">
            {batch.provider} · {batch.aspect_ratio} · {batch.duration_seconds}s ·{' '}
            {batch.variations_per_scenario} take{batch.variations_per_scenario === 1 ? '' : 's'} per scenario ·{' '}
            {new Date(batch.created_at).toLocaleString()}
          </p>
        </div>
        <StatusPill status={batch.status} />
      </div>

      {/* Audio mix panel — appears once any take is ready */}
      <AudioMixPanel batch={batch} onChange={refresh} />

      {/* Scenarios */}
      {scenarioGroups.map(({ scenario, takes }) => (
        <div key={scenario} className="critter-card mb-3">
          <div className="d-flex justify-content-between align-items-center mb-3">
            <h6 className="mb-0">
              <span className="badge bg-primary me-2">{scenario}</span>
              <small className="text-muted">{takes.length} take{takes.length === 1 ? '' : 's'}</small>
            </h6>
          </div>
          <div className="row g-3">
            {takes.map((take) => (
              <div key={take.uuid} className="col-md-4 col-lg-3">
                <TakeCard
                  take={take}
                  onRegenerate={() => regenerate(take.uuid)}
                  onCancel={() => cancel(take.uuid)}
                />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function TakeCard({ take, onRegenerate, onCancel }) {
  const url = take.video_asset?.signed_url;
  return (
    <div className="border rounded p-2">
      <div className="d-flex justify-content-between align-items-center mb-1">
        <small className="fw-semibold">Take {take.take_index + 1}</small>
        <StatusPill status={take.status} />
      </div>
      {url && take.status === 'succeeded' ? (
        <video src={url} controls loop muted playsInline
               className="w-100 rounded" style={{ aspectRatio: '9 / 16', objectFit: 'cover', background: '#000' }} />
      ) : (
        <div className="bg-light rounded d-flex align-items-center justify-content-center"
             style={{ aspectRatio: '9 / 16' }}>
          <small className="text-muted">
            {take.status === 'running' ? 'Generating…' :
             take.status === 'pending' ? 'Queued' :
             take.status === 'failed' ? 'Failed' : '—'}
          </small>
        </div>
      )}
      {take.caption && (
        <div className="mt-2">
          <small className="text-muted d-block">Caption</small>
          <small>{take.caption}</small>
          <button onClick={() => { navigator.clipboard.writeText(take.caption); toast.success('Copied'); }}
                  className="btn btn-sm btn-link p-0 ms-1"><Copy size={12} /></button>
        </div>
      )}
      {take.error_message && (
        <small className="text-danger d-block mt-1">{take.error_message.slice(0, 200)}</small>
      )}
      <div className="d-flex gap-1 mt-2">
        {url && (
          <a href={url} download={`take_${take.take_index + 1}.mp4`}
             className="btn btn-sm btn-outline-primary flex-grow-1 d-flex align-items-center justify-content-center gap-1">
            <Download size={12} /> Download
          </a>
        )}
        {['succeeded', 'failed'].includes(take.status) && (
          <button onClick={onRegenerate} className="btn btn-sm btn-outline-secondary">
            <RefreshCw size={12} />
          </button>
        )}
        {['pending', 'running'].includes(take.status) && (
          <button onClick={onCancel} className="btn btn-sm btn-outline-danger">Cancel</button>
        )}
      </div>
    </div>
  );
}

/**
 * AudioMixPanel — live-preview audio mix controls.
 *
 * The raw video plays with HTML <video>; volume slider updates `video.volume`
 * in real time, so you hear the change instantly. An optional music track
 * plays as a parallel <audio> element, synced to play/pause/seek with a
 * start offset. Changes auto-save as a draft on the batch; nothing is baked
 * to an MP4 until the user clicks "Bake mix" — which calls /remix/ to
 * produce new mixed MP4s for every take in the batch.
 *
 * Fades aren't live-previewed (volume ramps would need Web Audio API); they
 * only appear after baking. This is intentional + flagged in the UI.
 */
function AudioMixPanel({ batch, onChange }) {
  const [tracks, setTracks] = useState([]);
  const [previewTakeUuid, setPreviewTakeUuid] = useState('');
  const [originalVolume, setOriginalVolume] = useState(batch.original_audio_volume ?? 1.0);
  const [originalFadeIn, setOriginalFadeIn] = useState(batch.original_audio_fade_in_seconds ?? 0.0);
  const [originalFadeOut, setOriginalFadeOut] = useState(batch.original_audio_fade_out_seconds ?? 0.0);
  const [musicTrackUuid, setMusicTrackUuid] = useState(batch.music_track_uuid || '');
  const [musicVolume, setMusicVolume] = useState(batch.music_volume ?? 0.5);
  const [musicStartOffset, setMusicStartOffset] = useState(batch.music_start_offset_seconds ?? 0.0);
  const [musicFadeIn, setMusicFadeIn] = useState(batch.music_fade_in_seconds ?? 0.0);
  const [musicFadeOut, setMusicFadeOut] = useState(batch.music_fade_out_seconds ?? 0.0);
  const [saving, setSaving] = useState(false);
  const [baking, setBaking] = useState(false);
  const videoRef = useRef(null);
  const musicRef = useRef(null);

  useEffect(() => { api.get('/api/assets/audio/').then((r) => setTracks(r.data)); }, []);

  // Sync local state from the batch when it refreshes
  useEffect(() => {
    setOriginalVolume(batch.original_audio_volume ?? 1.0);
    setOriginalFadeIn(batch.original_audio_fade_in_seconds ?? 0.0);
    setOriginalFadeOut(batch.original_audio_fade_out_seconds ?? 0.0);
    setMusicTrackUuid(batch.music_track_uuid || '');
    setMusicVolume(batch.music_volume ?? 0.5);
    setMusicStartOffset(batch.music_start_offset_seconds ?? 0.0);
    setMusicFadeIn(batch.music_fade_in_seconds ?? 0.0);
    setMusicFadeOut(batch.music_fade_out_seconds ?? 0.0);
  }, [batch.uuid, batch.updated_at]);

  const succeededTakes = batch.generations.filter(
    (g) => g.status === 'succeeded' && g.video_asset_raw?.signed_url,
  );
  useEffect(() => {
    if (!previewTakeUuid && succeededTakes.length) setPreviewTakeUuid(succeededTakes[0].uuid);
  }, [succeededTakes.length]);

  const previewTake = batch.generations.find((g) => g.uuid === previewTakeUuid);
  const selectedTrack = tracks.find((t) => t.uuid === musicTrackUuid);

  // Live volume updates
  useEffect(() => { if (videoRef.current) videoRef.current.volume = Math.min(1, originalVolume); }, [originalVolume]);
  useEffect(() => { if (musicRef.current) musicRef.current.volume = Math.min(1, musicVolume); }, [musicVolume]);

  // Sync music play/pause/seek with video
  useEffect(() => {
    const v = videoRef.current; const m = musicRef.current;
    if (!v || !m) return;
    const onPlay = () => {
      m.currentTime = Math.min(m.duration || 0, musicStartOffset);
      m.play().catch(() => {});
    };
    const onPause = () => m.pause();
    const onSeeked = () => {
      m.currentTime = Math.min(m.duration || 0, musicStartOffset + (v.currentTime || 0));
    };
    v.addEventListener('play', onPlay);
    v.addEventListener('pause', onPause);
    v.addEventListener('seeked', onSeeked);
    return () => {
      v.removeEventListener('play', onPlay);
      v.removeEventListener('pause', onPause);
      v.removeEventListener('seeked', onSeeked);
    };
  }, [musicStartOffset, musicTrackUuid, previewTakeUuid]);

  // Auto-save draft settings to the batch (debounced) as user scrubs sliders.
  // We only save after 800ms of no change so we don't spam the API.
  const lastSaved = useRef({});
  useEffect(() => {
    const current = {
      original_audio_volume: originalVolume,
      original_audio_fade_in_seconds: originalFadeIn,
      original_audio_fade_out_seconds: originalFadeOut,
      music_track_uuid: musicTrackUuid || null,
      music_volume: musicVolume,
      music_start_offset_seconds: musicStartOffset,
      music_fade_in_seconds: musicFadeIn,
      music_fade_out_seconds: musicFadeOut,
    };
    if (JSON.stringify(current) === JSON.stringify(lastSaved.current)) return;
    const t = setTimeout(async () => {
      setSaving(true);
      try {
        await api.patch(`/api/generations/batches/${batch.uuid}/audio/`, current);
        lastSaved.current = current;
      } catch {}
      setSaving(false);
    }, 800);
    return () => clearTimeout(t);
  }, [originalVolume, originalFadeIn, originalFadeOut, musicTrackUuid,
      musicVolume, musicStartOffset, musicFadeIn, musicFadeOut]);

  const bake = async () => {
    setBaking(true);
    try {
      await api.post(`/api/generations/batches/${batch.uuid}/remix/`);
      toast.success('Baking mix into every take — refresh in a few seconds');
      setTimeout(() => { onChange(); setBaking(false); }, 4000);
    } catch (err) {
      toast.error(err.response?.data?.error || 'Remix failed');
      setBaking(false);
    }
  };

  const resetAll = () => {
    setOriginalVolume(1.0);
    setOriginalFadeIn(0); setOriginalFadeOut(0);
    setMusicTrackUuid(''); setMusicVolume(0.5);
    setMusicStartOffset(0); setMusicFadeIn(0); setMusicFadeOut(0);
  };

  if (!succeededTakes.length) return null;

  return (
    <div className="critter-card mb-3">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h5 className="mb-0"><Music size={18} className="me-2" />Audio mix</h5>
        <div className="d-flex gap-2 align-items-center">
          {saving && <small className="text-muted">Saving draft…</small>}
          <button onClick={resetAll} className="btn btn-sm btn-outline-secondary d-flex align-items-center gap-1">
            <RotateCcw size={12} /> Reset
          </button>
          <button onClick={bake} className="btn btn-sm btn-primary d-flex align-items-center gap-1" disabled={baking}>
            <Sparkles size={12} /> {baking ? 'Baking…' : 'Bake mix into every take'}
          </button>
        </div>
      </div>

      <div className="row g-3">
        {/* Preview */}
        <div className="col-md-5">
          <div className="border rounded p-3 h-100">
            <label className="form-label small d-block">Preview take</label>
            <select className="form-select form-select-sm mb-2" value={previewTakeUuid}
                    onChange={(e) => setPreviewTakeUuid(e.target.value)}>
              {succeededTakes.map((g) => (
                <option key={g.uuid} value={g.uuid}>
                  {g.scenario} — take {g.take_index + 1}
                </option>
              ))}
            </select>
            {previewTake && (
              <video ref={videoRef}
                     src={previewTake.video_asset_raw?.signed_url}
                     controls
                     className="w-100 rounded"
                     style={{ aspectRatio: '9 / 16', maxHeight: 400, objectFit: 'contain', background: '#000' }} />
            )}
            {selectedTrack?.signed_url && (
              <audio ref={musicRef} src={selectedTrack.signed_url} loop style={{ display: 'none' }} />
            )}
            <small className="text-muted d-block mt-2">
              🎧 Volumes update live as you drag. Fade in/out renders only after you <strong>Bake</strong> the mix.
              Draft auto-saves.
            </small>
          </div>
        </div>

        {/* Controls */}
        <div className="col-md-7">
          <div className="row g-2">
            <div className="col-md-6">
              <div className="border rounded p-2 h-100">
                <div className="fw-semibold small mb-1">Veo's native audio</div>
                <SliderRow label="Volume" value={originalVolume} setValue={setOriginalVolume} max={2} step={0.05}
                           hint={originalVolume === 0 ? 'Muted' : `${Math.round(originalVolume * 100)}%`} />
                <SliderRow label="Fade in" value={originalFadeIn} setValue={setOriginalFadeIn} max={5} step={0.1}
                           hint={`${originalFadeIn.toFixed(1)}s`} />
                <SliderRow label="Fade out" value={originalFadeOut} setValue={setOriginalFadeOut} max={5} step={0.1}
                           hint={`${originalFadeOut.toFixed(1)}s`} />
              </div>
            </div>
            <div className="col-md-6">
              <div className="border rounded p-2 h-100">
                <div className="d-flex justify-content-between align-items-center mb-1">
                  <span className="fw-semibold small">Music overlay</span>
                  <Link to="/music" className="small">Manage</Link>
                </div>
                <select className="form-select form-select-sm mb-2"
                        value={musicTrackUuid} onChange={(e) => setMusicTrackUuid(e.target.value)}>
                  <option value="">— No music —</option>
                  {tracks.map((t) => (
                    <option key={t.uuid} value={t.uuid}>{t.original_filename}</option>
                  ))}
                </select>
                <SliderRow label="Volume" value={musicVolume} setValue={setMusicVolume} max={2} step={0.05}
                           disabled={!musicTrackUuid}
                           hint={musicVolume === 0 ? 'Muted' : `${Math.round(musicVolume * 100)}%`} />
                <SliderRow label="Start at" value={musicStartOffset} setValue={setMusicStartOffset}
                           max={300} step={0.5} disabled={!musicTrackUuid}
                           hint={`${musicStartOffset.toFixed(1)}s`} />
                <SliderRow label="Fade in" value={musicFadeIn} setValue={setMusicFadeIn} max={5} step={0.1}
                           disabled={!musicTrackUuid} hint={`${musicFadeIn.toFixed(1)}s`} />
                <SliderRow label="Fade out" value={musicFadeOut} setValue={setMusicFadeOut} max={5} step={0.1}
                           disabled={!musicTrackUuid} hint={`${musicFadeOut.toFixed(1)}s`} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function SliderRow({ label, value, setValue, min = 0, max = 1, step = 0.05, hint = '', disabled = false }) {
  return (
    <div className="d-flex align-items-center gap-2 mb-1">
      <small className="text-muted" style={{ width: 60, flexShrink: 0, fontSize: 11 }}>{label}</small>
      <input type="range" className="form-range flex-grow-1"
             min={min} max={max} step={step} value={value}
             onChange={(e) => setValue(parseFloat(e.target.value))}
             disabled={disabled} />
      <small className="text-muted text-end" style={{ width: 70, flexShrink: 0, fontSize: 11 }}>{hint}</small>
    </div>
  );
}
