import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Sparkles } from 'lucide-react';
import api from '../api';

export default function ThemeListPage() {
  const [themes, setThemes] = useState([]);

  useEffect(() => {
    api.get('/api/themes/').then((r) => setThemes(r.data));
  }, []);

  const featured = themes.filter((t) => t.is_featured);
  const others = themes.filter((t) => !t.is_featured);

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-4">
        <div>
          <h2 className="mb-1">Themes</h2>
          <p className="text-muted mb-0">Reusable templates that define the style + structure of your videos</p>
        </div>
        <Link to="/generate" className="btn btn-primary d-flex align-items-center gap-2">
          <Sparkles size={16} /> Generate with a theme
        </Link>
      </div>

      {featured.length > 0 && (
        <>
          <h6 className="text-muted small mb-2">FEATURED</h6>
          <div className="row g-3 mb-4">
            {featured.map((t) => <ThemeTile key={t.uuid} theme={t} />)}
          </div>
        </>
      )}

      {others.length > 0 && (
        <>
          <h6 className="text-muted small mb-2">ALL THEMES</h6>
          <div className="row g-3">
            {others.map((t) => <ThemeTile key={t.uuid} theme={t} />)}
          </div>
        </>
      )}
    </div>
  );
}

function ThemeTile({ theme }) {
  return (
    <div className="col-md-6 col-lg-4">
      <Link to={`/generate?theme=${theme.uuid}`} className="theme-tile">
        <div className="d-flex align-items-center gap-2 mb-2">
          {theme.cover_emoji && <span style={{ fontSize: 32 }}>{theme.cover_emoji}</span>}
          <div>
            <div className="fw-semibold">{theme.name}</div>
            <small className="text-muted">{theme.shot_style} · {theme.music_vibe}</small>
          </div>
        </div>
        <p className="small text-muted mb-2">{theme.description}</p>
        {theme.tags?.length > 0 && (
          <div className="d-flex gap-1 flex-wrap">
            {theme.tags.slice(0, 4).map((tag) => (
              <span key={tag} className="badge bg-light text-dark small">{tag}</span>
            ))}
          </div>
        )}
      </Link>
    </div>
  );
}
