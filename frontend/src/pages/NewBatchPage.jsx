import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { Plus, Sparkles, X } from 'lucide-react';
import { toast } from 'react-toastify';
import api from '../api';

export default function NewBatchPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();

  const [subjects, setSubjects] = useState([]);
  const [themes, setThemes] = useState([]);
  const [subjectUuid, setSubjectUuid] = useState(params.get('subject') || '');
  const [themeUuid, setThemeUuid] = useState(params.get('theme') || '');
  const [scenarios, setScenarios] = useState(['']);
  const [variationsPerScenario, setVariationsPerScenario] = useState(1);
  const [provider, setProvider] = useState('veo_31_lite');
  const [aspectRatio, setAspectRatio] = useState('9:16');
  const [duration, setDuration] = useState(8);
  const [extraDetail, setExtraDetail] = useState('');
  const [expandPrompts, setExpandPrompts] = useState(true);
  const [genCaptions, setGenCaptions] = useState(true);
  const [usePhotoBackground, setUsePhotoBackground] = useState(true);
  const [personGeneration, setPersonGeneration] = useState('allow_adult');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    Promise.all([api.get('/api/subjects/'), api.get('/api/themes/')]).then(([s, t]) => {
      setSubjects(s.data);
      setThemes(t.data);
    });
  }, []);

  const selectedTheme = themes.find((t) => t.uuid === themeUuid);

  useEffect(() => {
    if (selectedTheme && selectedTheme.default_scenarios?.length && scenarios.every((s) => !s.trim())) {
      setScenarios(selectedTheme.default_scenarios.slice(0, 3));
    }
  }, [selectedTheme]);

  const addScenario = () => setScenarios([...scenarios, '']);
  const updateScenario = (i, v) => setScenarios(scenarios.map((s, idx) => (idx === i ? v : s)));
  const removeScenario = (i) => setScenarios(scenarios.filter((_, idx) => idx !== i));

  const cleanedScenarios = scenarios.map((s) => s.trim()).filter(Boolean);
  const totalVideos = cleanedScenarios.length * variationsPerScenario;

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!subjectUuid) return toast.error('Pick a pet');
    if (!themeUuid) return toast.error('Pick a theme');
    if (!cleanedScenarios.length) return toast.error('Add at least one scenario');

    setSubmitting(true);
    try {
      const res = await api.post('/api/generations/batches/create/', {
        subject_uuid: subjectUuid,
        theme_uuid: themeUuid,
        scenarios: cleanedScenarios,
        variations_per_scenario: variationsPerScenario,
        provider,
        aspect_ratio: aspectRatio,
        duration_seconds: duration,
        extra_detail: extraDetail,
        expand_prompts_with_claude: expandPrompts,
        generate_captions: genCaptions,
        use_photo_background: usePhotoBackground,
        person_generation: personGeneration,
      });
      toast.success(`Started ${totalVideos} generation${totalVideos === 1 ? '' : 's'}`);
      navigate(`/generations/${res.data.uuid}`);
    } catch (err) {
      const msg = err.response?.data?.error || 'Could not start batch';
      toast.error(msg);
    }
    setSubmitting(false);
  };

  return (
    <div>
      <div className="mb-4">
        <h2 className="mb-1">Generate videos</h2>
        <p className="text-muted mb-0">
          Pick a pet + theme, add scenarios. Each scenario can produce multiple takes with different seeds.
          Audio (music + volumes + fades) is tuned <strong>after</strong> generation on the batch detail page — no need to commit now.
        </p>
      </div>

      <form onSubmit={onSubmit}>
        <div className="critter-card mb-3">
          <h6 className="mb-3">1. Choose pet</h6>
          {subjects.length === 0 ? (
            <p className="text-muted small mb-0">
              No pets yet. <Link to="/subjects">Create one first →</Link>
            </p>
          ) : (
            <select className="form-select" value={subjectUuid} onChange={(e) => setSubjectUuid(e.target.value)}>
              <option value="">— Select pet —</option>
              {subjects.map((s) => (
                <option key={s.uuid} value={s.uuid}>{s.name} ({s.species || s.kind})</option>
              ))}
            </select>
          )}
        </div>

        <div className="critter-card mb-3">
          <h6 className="mb-3">2. Choose theme</h6>
          <div className="row g-2">
            {themes.map((t) => (
              <div key={t.uuid} className="col-md-6 col-lg-4">
                <div
                  onClick={() => setThemeUuid(t.uuid)}
                  className={`theme-tile ${themeUuid === t.uuid ? 'selected' : ''}`}
                  style={{ cursor: 'pointer' }}
                >
                  <div className="d-flex align-items-center gap-2">
                    {t.cover_emoji && <span style={{ fontSize: 28 }}>{t.cover_emoji}</span>}
                    <div>
                      <div className="fw-semibold">{t.name}</div>
                      <small className="text-muted">{t.shot_style}</small>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="critter-card mb-3">
          <div className="d-flex justify-content-between align-items-center mb-3">
            <h6 className="mb-0">3. Scenarios + takes</h6>
            <div className="d-flex align-items-center gap-2">
              <label className="form-label small mb-0">Takes per scenario:</label>
              <select className="form-select form-select-sm" style={{ width: 80 }}
                      value={variationsPerScenario}
                      onChange={(e) => setVariationsPerScenario(Number(e.target.value))}>
                {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
          </div>
          {scenarios.map((s, i) => (
            <div key={i} className="d-flex gap-2 mb-2">
              <input
                className="form-control"
                placeholder={selectedTheme?.default_scenarios?.[i] || 'e.g. tiny pancakes'}
                value={s}
                onChange={(e) => updateScenario(i, e.target.value)}
              />
              {scenarios.length > 1 && (
                <button type="button" onClick={() => removeScenario(i)} className="btn btn-outline-secondary">
                  <X size={14} />
                </button>
              )}
            </div>
          ))}
          <button type="button" onClick={addScenario} className="btn btn-sm btn-outline-primary d-flex align-items-center gap-1">
            <Plus size={14} /> Add scenario
          </button>
          {totalVideos > 0 && (
            <small className="text-muted d-block mt-2">
              Will generate <strong>{totalVideos}</strong> video{totalVideos === 1 ? '' : 's'} total
              ({cleanedScenarios.length} scenario{cleanedScenarios.length === 1 ? '' : 's'} × {variationsPerScenario} take{variationsPerScenario === 1 ? '' : 's'}). Each take uses a different seed.
            </small>
          )}
        </div>

        <div className="critter-card mb-3">
          <h6 className="mb-3">4. Options</h6>
          <div className="row g-3">
            <div className="col-md-4">
              <label className="form-label small">Video model</label>
              <select className="form-select" value={provider} onChange={(e) => setProvider(e.target.value)}>
                <optgroup label="Veo 3.1 (newest)">
                  <option value="veo_31_lite">Veo 3.1 Lite — cheapest, fastest</option>
                  <option value="veo_31_fast">Veo 3.1 Fast — balanced</option>
                  <option value="veo_31">Veo 3.1 Standard — best quality</option>
                </optgroup>
                <optgroup label="Veo 3.0 (older but stable)">
                  <option value="veo_30_fast">Veo 3.0 Fast</option>
                  <option value="veo_30">Veo 3.0 Standard</option>
                </optgroup>
                <optgroup label="Runway">
                  <option value="runway_gen3">Runway Gen-3 Alpha Turbo — cheap legacy (image-to-video)</option>
                  <option value="runway_gen4">Runway Gen-4 Turbo — fastest (image-to-video)</option>
                  <option value="runway_gen4_5">Runway Gen-4.5 — state-of-the-art (text + image)</option>
                </optgroup>
                <optgroup label="Kling (Kuaishou)">
                  <option value="kling_21">Kling 2.1 Master — premium cinematic</option>
                </optgroup>
              </select>
            </div>
            <div className="col-md-4">
              <label className="form-label small">Aspect ratio</label>
              <select className="form-select" value={aspectRatio} onChange={(e) => setAspectRatio(e.target.value)}>
                <option value="9:16">9:16 (Reels / TikTok)</option>
                <option value="1:1">1:1 (Square)</option>
                <option value="16:9">16:9 (YouTube)</option>
              </select>
            </div>
            <div className="col-md-4">
              <label className="form-label small">Duration</label>
              <select className="form-select" value={duration}
                      onChange={(e) => setDuration(Number(e.target.value))}>
                <option value={4}>4 seconds</option>
                <option value={6}>6 seconds</option>
                <option value={8}>8 seconds</option>
              </select>
            </div>
            <div className="col-md-12">
              <label className="form-label small">Extra direction (applies to every video)</label>
              <textarea className="form-control" rows={2}
                        placeholder="e.g. golden hour lighting, slightly fluffy fur"
                        value={extraDetail} onChange={(e) => setExtraDetail(e.target.value)} />
            </div>
            <div className="col-md-6">
              <div className="form-check">
                <input className="form-check-input" type="checkbox" checked={expandPrompts}
                       onChange={(e) => setExpandPrompts(e.target.checked)} id="exp" />
                <label className="form-check-label small" htmlFor="exp">
                  Polish prompts with Claude (recommended)
                </label>
              </div>
            </div>
            <div className="col-md-6">
              <div className="form-check">
                <input className="form-check-input" type="checkbox" checked={genCaptions}
                       onChange={(e) => setGenCaptions(e.target.checked)} id="cap" />
                <label className="form-check-label small" htmlFor="cap">
                  Generate captions with Claude
                </label>
              </div>
            </div>

            <div className="col-md-12 mt-2">
              <div className="border rounded p-3" style={{ background: '#f8fafc' }}>
                <div className="form-check mb-1">
                  <input className="form-check-input" type="checkbox" checked={usePhotoBackground}
                         onChange={(e) => setUsePhotoBackground(e.target.checked)} id="usebg" />
                  <label className="form-check-label small fw-semibold" htmlFor="usebg">
                    Use the primary photo's background
                  </label>
                </div>
                <small className="text-muted d-block" style={{ paddingLeft: 24 }}>
                  {usePhotoBackground
                    ? 'Your photo is used as the first frame — pet looks exact, and the photo\'s background carries through to every video.'
                    : 'Your photo is still passed as a character reference (so the pet looks right), but the prompt explicitly tells the model to generate a fresh scene and ignore the photo\'s background. Best of both worlds.'}
                </small>
              </div>
            </div>

            <div className="col-md-12">
              <label className="form-label small fw-semibold mb-1">People in videos</label>
              <select className="form-select form-select-sm"
                      value={personGeneration} onChange={(e) => setPersonGeneration(e.target.value)}>
                <option value="allow_adult">Allow people (recommended) — Veo decides if any are needed; no minors</option>
                <option value="dont_allow">No people in videos — both Veo + the prompt enforce no humans</option>
                <option value="allow_all">Allow everyone, including kids (rare)</option>
              </select>
            </div>
          </div>
        </div>

        <div className="d-flex justify-content-end gap-2">
          <button type="button" onClick={() => navigate('/generations')} className="btn btn-outline-secondary">
            Cancel
          </button>
          <button type="submit" className="btn btn-primary d-flex align-items-center gap-2" disabled={submitting}>
            <Sparkles size={16} />
            {submitting ? 'Starting…' : `Generate ${totalVideos || ''} video${totalVideos === 1 ? '' : 's'}`}
          </button>
        </div>
      </form>
    </div>
  );
}
