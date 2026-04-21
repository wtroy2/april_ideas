import { useEffect, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ArrowLeft, Sparkles, RefreshCw, Plus, Trash2, Check,
  Film, Scissors, Download, Copy,
} from 'lucide-react';
import { toast } from 'react-toastify';
import api from '../api';
import { StatusPill } from './DashboardPage';

export default function StoryDetailPage() {
  const { uuid } = useParams();
  const [story, setStory] = useState(null);
  const pollRef = useRef(null);

  const refresh = () => api.get(`/api/stories/${uuid}/`).then((r) => setStory(r.data));
  useEffect(() => { refresh(); }, [uuid]);

  // Poll while anything is active
  useEffect(() => {
    if (!story) return;
    const active = ['planning', 'generating', 'stitching'].includes(story.status)
      || story.scenes.some((s) => s.takes.some((t) => ['pending', 'running'].includes(t.status)));
    if (!active) { if (pollRef.current) clearInterval(pollRef.current); return; }
    pollRef.current = setInterval(refresh, 4000);
    return () => clearInterval(pollRef.current);
  }, [story?.status, story?.scenes]);

  if (!story) return <div>Loading…</div>;

  const totalDuration = story.total_duration_seconds;
  const allScenesHavePick = story.scenes.every((s) => s.chosen_generation_uuid);
  const anyTakes = story.scenes.some((s) => s.takes.length > 0);
  const canStitch = allScenesHavePick && story.status !== 'stitching';

  const replan = async () => {
    if (anyTakes && !confirm('Replanning will wipe existing scenes + their takes. Continue?')) return;
    await api.post(`/api/stories/${uuid}/replan/`);
    toast.info('Re-planning with Claude…');
    refresh();
  };

  const generateAll = async () => {
    await api.post(`/api/stories/${uuid}/generate-all/`);
    toast.success('Started generating takes for every scene');
    refresh();
  };

  const stitch = async () => {
    try {
      await api.post(`/api/stories/${uuid}/stitch/`);
      toast.success('Stitching the final video…');
      refresh();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Stitch failed');
    }
  };

  return (
    <div>
      <Link to="/stories" className="small text-muted text-decoration-none d-inline-flex align-items-center gap-1 mb-3">
        <ArrowLeft size={14} /> All stories
      </Link>

      {/* Header */}
      <div className="d-flex justify-content-between align-items-start mb-4">
        <div>
          <h2 className="mb-1">{story.title || <em className="text-muted">Untitled story</em>}</h2>
          <p className="text-muted mb-1">{story.subject_name} · {story.provider} · {story.aspect_ratio}</p>
          <p className="mb-0"><em className="text-muted">"{story.concept}"</em></p>
        </div>
        <div className="text-end">
          <StatusPill status={story.status.replace(/_/g, ' ')} />
          <div className="text-muted small mt-1">
            {totalDuration}s / target {story.target_duration_seconds}s · {story.scenes.length} scenes
          </div>
        </div>
      </div>

      {/* Error banner */}
      {story.error_message && (
        <div className="alert alert-danger small">{story.error_message}</div>
      )}

      {/* Final stitched video */}
      {story.final_video_asset?.signed_url && (
        <div className="critter-card mb-3">
          <div className="d-flex justify-content-between align-items-center mb-2">
            <h5 className="mb-0"><Film size={18} className="me-2" />Final video</h5>
            <a href={story.final_video_asset.signed_url}
               download={`${story.title || 'story'}.mp4`}
               className="btn btn-sm btn-outline-primary d-flex align-items-center gap-1">
              <Download size={14} /> Download
            </a>
          </div>
          <video src={story.final_video_asset.signed_url} controls
                 className="w-100 rounded" style={{ maxHeight: 600, background: '#000' }} />
        </div>
      )}

      {/* Action bar */}
      <div className="d-flex gap-2 flex-wrap mb-3">
        <button onClick={replan} className="btn btn-outline-secondary btn-sm d-flex align-items-center gap-1"
                disabled={story.status === 'planning' || story.status === 'generating'}>
          <RefreshCw size={14} /> Replan with Claude
        </button>
        {story.scenes.length > 0 && (
          <button onClick={generateAll} className="btn btn-primary btn-sm d-flex align-items-center gap-1"
                  disabled={['planning', 'generating', 'stitching'].includes(story.status)}>
            <Sparkles size={14} /> Generate all scene takes
          </button>
        )}
        {anyTakes && (
          <button onClick={stitch} className="btn btn-success btn-sm d-flex align-items-center gap-1"
                  disabled={!canStitch}>
            <Scissors size={14} /> Stitch final video
            {!allScenesHavePick && <small className="ms-1">(pick a take per scene first)</small>}
          </button>
        )}
      </div>

      {/* Scenes */}
      {story.status === 'planning' && story.scenes.length === 0 && (
        <div className="critter-card critter-empty-state">
          <Sparkles size={32} className="text-primary mb-2" />
          <p className="mb-0">Claude is planning your scenes… this usually takes 5–15 seconds.</p>
        </div>
      )}

      {story.scenes.map((scene) => (
        <SceneCard key={scene.id} story={story} scene={scene} onChange={refresh} />
      ))}

      <div className="text-center mt-3">
        <button onClick={async () => {
          const order = story.scenes.length;
          await api.post(`/api/stories/${uuid}/scenes/add/`, {
            order,
            title: `Scene ${order + 1}`,
            prompt: 'Describe this scene…',
            duration_seconds: story.per_scene_duration_seconds,
          });
          refresh();
        }} className="btn btn-sm btn-outline-primary d-flex align-items-center gap-1 mx-auto">
          <Plus size={14} /> Add scene at end
        </button>
      </div>
    </div>
  );
}

function SceneCard({ story, scene, onChange }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({
    title: scene.title,
    prompt: scene.prompt,
    duration_seconds: scene.duration_seconds,
    desired_takes: scene.desired_takes,
    transition_out: scene.transition_out,
  });

  useEffect(() => {
    setDraft({
      title: scene.title,
      prompt: scene.prompt,
      duration_seconds: scene.duration_seconds,
      desired_takes: scene.desired_takes,
      transition_out: scene.transition_out,
    });
  }, [scene.id, scene.updated_at]);

  const save = async () => {
    await api.patch(`/api/stories/${story.uuid}/scenes/${scene.id}/`, draft);
    setEditing(false);
    onChange();
  };

  const remove = async () => {
    if (!confirm(`Delete scene "${scene.title}"? Will also delete its takes.`)) return;
    await api.delete(`/api/stories/${story.uuid}/scenes/${scene.id}/delete/`);
    onChange();
  };

  const generate = async () => {
    await api.post(`/api/stories/${story.uuid}/scenes/${scene.id}/generate/`);
    toast.success(`Generating ${scene.desired_takes} take(s) for "${scene.title}"`);
    onChange();
  };

  const pick = async (take) => {
    await api.post(`/api/stories/${story.uuid}/scenes/${scene.id}/pick/${take.uuid}/`);
    onChange();
  };

  return (
    <div className="critter-card mb-3">
      <div className="d-flex justify-content-between align-items-start mb-2">
        <div className="d-flex align-items-center gap-2">
          <span className="badge bg-primary">{scene.order + 1}</span>
          {editing ? (
            <input className="form-control form-control-sm" style={{ minWidth: 300 }}
                   value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          ) : (
            <h6 className="mb-0">{scene.title}</h6>
          )}
          <small className="text-muted">· {scene.duration_seconds}s · {scene.desired_takes} take{scene.desired_takes === 1 ? '' : 's'}</small>
        </div>
        <div className="d-flex gap-1">
          {!editing && (
            <>
              <button onClick={() => setEditing(true)} className="btn btn-sm btn-outline-secondary">Edit</button>
              <button onClick={generate} className="btn btn-sm btn-primary d-flex align-items-center gap-1">
                <Sparkles size={12} /> {scene.takes.length > 0 ? 'Regenerate' : 'Generate'}
              </button>
              <button onClick={remove} className="btn btn-sm btn-outline-danger"><Trash2 size={12} /></button>
            </>
          )}
          {editing && (
            <>
              <button onClick={() => setEditing(false)} className="btn btn-sm btn-outline-secondary">Cancel</button>
              <button onClick={save} className="btn btn-sm btn-success">Save</button>
            </>
          )}
        </div>
      </div>

      {/* Prompt + options */}
      {editing ? (
        <div className="row g-2">
          <div className="col-md-12">
            <label className="form-label small">Prompt (this is what the video model sees)</label>
            <textarea className="form-control form-control-sm" rows={3}
                      value={draft.prompt} onChange={(e) => setDraft({ ...draft, prompt: e.target.value })} />
            <button
              onClick={() => { navigator.clipboard.writeText(draft.prompt); toast.success('Copied'); }}
              className="btn btn-link btn-sm p-0 mt-1">
              <Copy size={12} /> Copy prompt
            </button>
          </div>
          <div className="col-md-4">
            <label className="form-label small">Duration</label>
            <select className="form-select form-select-sm"
                    value={draft.duration_seconds}
                    onChange={(e) => setDraft({ ...draft, duration_seconds: Number(e.target.value) })}>
              <option value={4}>4s</option>
              <option value={6}>6s</option>
              <option value={8}>8s</option>
            </select>
          </div>
          <div className="col-md-4">
            <label className="form-label small">Takes (variations)</label>
            <select className="form-select form-select-sm"
                    value={draft.desired_takes}
                    onChange={(e) => setDraft({ ...draft, desired_takes: Number(e.target.value) })}>
              {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <div className="col-md-4">
            <label className="form-label small">Transition to next scene</label>
            <select className="form-select form-select-sm"
                    value={draft.transition_out}
                    onChange={(e) => setDraft({ ...draft, transition_out: e.target.value })}>
              <option value="cut">Hard cut</option>
              <option value="crossfade">Crossfade (0.5s)</option>
              <option value="fade_black">Fade through black (0.5s)</option>
            </select>
          </div>
        </div>
      ) : (
        <p className="small text-muted mb-0" style={{ whiteSpace: 'pre-wrap' }}>{scene.prompt}</p>
      )}

      {/* Takes */}
      {scene.takes.length > 0 && (
        <div className="mt-3">
          <div className="row g-2">
            {scene.takes.map((take, i) => (
              <TakeTile key={take.uuid} take={take} index={i} isChosen={scene.chosen_generation_uuid === take.uuid}
                        onPick={() => pick(take)} />
            ))}
          </div>
          {!scene.chosen_generation_uuid && scene.takes.some((t) => t.status === 'succeeded') && (
            <small className="text-muted d-block mt-2">
              👆 Click a take to pick it as the one used in the final stitched video.
            </small>
          )}
        </div>
      )}
    </div>
  );
}

function TakeTile({ take, index, isChosen, onPick }) {
  const color = {
    pending: 'secondary', running: 'info',
    succeeded: 'success', failed: 'danger', cancelled: 'warning',
  }[take.status] || 'secondary';

  return (
    <div className="col-md-4 col-lg-3">
      <div
        onClick={take.status === 'succeeded' ? onPick : undefined}
        className={`border rounded p-2 ${isChosen ? 'border-primary bg-light' : ''}`}
        style={{ cursor: take.status === 'succeeded' ? 'pointer' : 'default' }}>
        <div className="d-flex justify-content-between align-items-center mb-1">
          <small className="fw-semibold">Take {index + 1}</small>
          {isChosen ? (
            <span className="badge bg-primary d-flex align-items-center gap-1"><Check size={10} /> Chosen</span>
          ) : (
            <span className={`badge bg-${color}`}>{take.status}</span>
          )}
        </div>
        {take.video_asset_raw?.signed_url || take.video_asset?.signed_url ? (
          <video src={take.video_asset_raw?.signed_url || take.video_asset?.signed_url}
                 className="w-100 rounded" loop muted playsInline
                 style={{ aspectRatio: '9 / 16', objectFit: 'cover', background: '#000', pointerEvents: 'none' }}
                 onMouseEnter={(e) => e.currentTarget.play()}
                 onMouseLeave={(e) => { e.currentTarget.pause(); e.currentTarget.currentTime = 0; }} />
        ) : (
          <div className="bg-light rounded d-flex align-items-center justify-content-center"
               style={{ aspectRatio: '9 / 16' }}>
            <small className="text-muted">
              {take.status === 'running' ? 'Generating…' :
               take.status === 'failed' ? 'Failed' : 'Queued'}
            </small>
          </div>
        )}
        {take.error_message && (
          <small className="text-danger d-block mt-1" style={{ fontSize: 10 }}>{take.error_message.slice(0, 100)}</small>
        )}
      </div>
    </div>
  );
}
