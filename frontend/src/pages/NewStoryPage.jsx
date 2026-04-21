import { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Film, Sparkles } from 'lucide-react';
import { toast } from 'react-toastify';
import api from '../api';

export default function NewStoryPage() {
  const navigate = useNavigate();
  const [subjects, setSubjects] = useState([]);
  const [themes, setThemes] = useState([]);

  const [subjectUuid, setSubjectUuid] = useState('');
  const [themeUuid, setThemeUuid] = useState('');
  const [title, setTitle] = useState('');
  const [concept, setConcept] = useState('');
  const [targetDuration, setTargetDuration] = useState(30);
  const [perScene, setPerScene] = useState(8);
  const [provider, setProvider] = useState('veo_31_lite');
  const [aspectRatio, setAspectRatio] = useState('9:16');
  const [extraDetail, setExtraDetail] = useState('');
  const [usePhotoBackground, setUsePhotoBackground] = useState(false);  // default OFF for stories — fresh scenes
  const [personGeneration, setPersonGeneration] = useState('allow_adult');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    Promise.all([api.get('/api/subjects/'), api.get('/api/themes/')]).then(([s, t]) => {
      setSubjects(s.data);
      setThemes(t.data);
    });
  }, []);

  const sceneCountEstimate = Math.max(2, Math.min(10, Math.round(targetDuration / perScene)));

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!subjectUuid) return toast.error('Pick a pet');
    if (!concept.trim()) return toast.error('Write a concept');
    setSubmitting(true);
    try {
      const res = await api.post('/api/stories/create/', {
        subject_uuid: subjectUuid,
        theme_uuid: themeUuid || null,
        title,
        concept,
        target_duration_seconds: targetDuration,
        per_scene_duration_seconds: perScene,
        provider,
        aspect_ratio: aspectRatio,
        extra_detail: extraDetail,
        expand_prompts_with_claude: true,
        use_photo_background: usePhotoBackground,
        person_generation: personGeneration,
      });
      toast.success('Story created — Claude is planning scenes now');
      navigate(`/stories/${res.data.uuid}`);
    } catch (err) {
      toast.error(err.response?.data?.error || 'Could not create story');
    }
    setSubmitting(false);
  };

  return (
    <div>
      <div className="mb-4">
        <h2 className="mb-1"><Film size={24} className="me-2" />New story</h2>
        <p className="text-muted mb-0">
          Claude breaks your concept into scenes, you review + edit, generate takes per scene, pick favorites, we stitch it all together.
        </p>
      </div>

      <form onSubmit={onSubmit}>
        <div className="critter-card mb-3">
          <h6 className="mb-3">1. The pitch</h6>
          <div className="row g-3">
            <div className="col-md-6">
              <label className="form-label small">Pet</label>
              {subjects.length === 0 ? (
                <p className="text-muted small mb-0">No pets yet. <Link to="/subjects">Create one first →</Link></p>
              ) : (
                <select className="form-select" value={subjectUuid} onChange={(e) => setSubjectUuid(e.target.value)}>
                  <option value="">— Select pet —</option>
                  {subjects.map((s) => (
                    <option key={s.uuid} value={s.uuid}>{s.name}</option>
                  ))}
                </select>
              )}
            </div>
            <div className="col-md-6">
              <label className="form-label small">Theme (optional — style hint for Claude)</label>
              <select className="form-select" value={themeUuid} onChange={(e) => setThemeUuid(e.target.value)}>
                <option value="">— None —</option>
                {themes.map((t) => (
                  <option key={t.uuid} value={t.uuid}>{t.name}</option>
                ))}
              </select>
            </div>
            <div className="col-md-12">
              <label className="form-label small">Title (optional)</label>
              <input className="form-control" value={title} onChange={(e) => setTitle(e.target.value)}
                     placeholder="e.g. Mr Kitty conquers Antarctica" />
            </div>
            <div className="col-md-12">
              <label className="form-label small">Concept — one or two sentences</label>
              <textarea className="form-control" rows={3} required
                        placeholder="e.g. Mr Kitty discovers Antarctica from a space ship, befriends a penguin, and heads home to nap on the couch."
                        value={concept} onChange={(e) => setConcept(e.target.value)} />
              <small className="text-muted">
                Claude will break this into ~{sceneCountEstimate} scenes. You can edit, add, remove, or reorder scenes before anything is generated.
              </small>
            </div>
          </div>
        </div>

        <div className="critter-card mb-3">
          <h6 className="mb-3">2. Length + model</h6>
          <div className="row g-3">
            <div className="col-md-4">
              <label className="form-label small">Target total length</label>
              <select className="form-select" value={targetDuration} onChange={(e) => setTargetDuration(Number(e.target.value))}>
                <option value={16}>~15 seconds</option>
                <option value={24}>~25 seconds</option>
                <option value={30}>~30 seconds</option>
                <option value={45}>~45 seconds</option>
                <option value={60}>~60 seconds (IG Reel max)</option>
                <option value={90}>~90 seconds</option>
                <option value={120}>~2 minutes</option>
              </select>
            </div>
            <div className="col-md-4">
              <label className="form-label small">Duration per scene</label>
              <select className="form-select" value={perScene} onChange={(e) => setPerScene(Number(e.target.value))}>
                <option value={4}>4s (more scenes, faster cuts)</option>
                <option value={6}>6s</option>
                <option value={8}>8s (fewer scenes, longer shots)</option>
              </select>
            </div>
            <div className="col-md-4">
              <label className="form-label small">Aspect ratio</label>
              <select className="form-select" value={aspectRatio} onChange={(e) => setAspectRatio(e.target.value)}>
                <option value="9:16">9:16 (Reels / TikTok)</option>
                <option value="1:1">1:1</option>
                <option value="16:9">16:9</option>
              </select>
            </div>
            <div className="col-md-12">
              <label className="form-label small">Video model (same for every scene)</label>
              <select className="form-select" value={provider} onChange={(e) => setProvider(e.target.value)}>
                <optgroup label="Veo 3.1">
                  <option value="veo_31_lite">Veo 3.1 Lite — cheapest</option>
                  <option value="veo_31_fast">Veo 3.1 Fast</option>
                  <option value="veo_31">Veo 3.1 Standard</option>
                </optgroup>
                <optgroup label="Veo 3.0">
                  <option value="veo_30_fast">Veo 3.0 Fast</option>
                  <option value="veo_30">Veo 3.0 Standard</option>
                </optgroup>
                <optgroup label="Runway">
                  <option value="runway_gen3">Runway Gen-3 Alpha Turbo</option>
                  <option value="runway_gen4">Runway Gen-4 Turbo</option>
                  <option value="runway_gen4_5">Runway Gen-4.5 — state-of-the-art</option>
                </optgroup>
                <optgroup label="Kling">
                  <option value="kling_21">Kling 2.1 Master</option>
                </optgroup>
              </select>
              <small className="text-muted">
                Estimated total cost = scenes × takes-per-scene × model cost. Start cheap (Lite) to iterate on the plan, upgrade for hero takes.
              </small>
            </div>
          </div>
        </div>

        <div className="critter-card mb-3">
          <h6 className="mb-3">3. Options</h6>
          <div className="row g-3">
            <div className="col-md-12">
              <label className="form-label small">Extra direction (applies to every scene)</label>
              <textarea className="form-control" rows={2}
                        placeholder="e.g. golden hour lighting throughout, cinematic shallow depth of field"
                        value={extraDetail} onChange={(e) => setExtraDetail(e.target.value)} />
            </div>
            <div className="col-md-12">
              <div className="form-check">
                <input className="form-check-input" type="checkbox" checked={usePhotoBackground}
                       onChange={(e) => setUsePhotoBackground(e.target.checked)} id="usebg" />
                <label className="form-check-label small" htmlFor="usebg">
                  Use the primary photo's background for all scenes
                </label>
              </div>
              <small className="text-muted d-block" style={{ paddingLeft: 24 }}>
                Stories usually want fresh backgrounds per scene — defaulted OFF. Turn ON only if your story stays in one location.
              </small>
            </div>
            <div className="col-md-12">
              <label className="form-label small">People in videos</label>
              <select className="form-select form-select-sm" value={personGeneration}
                      onChange={(e) => setPersonGeneration(e.target.value)}>
                <option value="allow_adult">Allow people (recommended)</option>
                <option value="dont_allow">No people in any scene</option>
                <option value="allow_all">Allow everyone, including kids</option>
              </select>
            </div>
          </div>
        </div>

        <div className="d-flex justify-content-end gap-2">
          <button type="button" onClick={() => navigate('/stories')} className="btn btn-outline-secondary">Cancel</button>
          <button type="submit" className="btn btn-primary d-flex align-items-center gap-2" disabled={submitting}>
            <Sparkles size={16} />
            {submitting ? 'Creating…' : 'Plan with Claude →'}
          </button>
        </div>
      </form>
    </div>
  );
}
