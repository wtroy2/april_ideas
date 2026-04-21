import { useContext, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Sparkles, PawPrint, Palette, Film, Plus } from 'lucide-react';
import api from '../api';
import { AuthContext } from '../context/AuthContext';

export default function DashboardPage() {
  const { firstname, organizationStatus } = useContext(AuthContext);
  const [counts, setCounts] = useState({ subjects: 0, themes: 0, batches: 0 });
  const [recentBatches, setRecentBatches] = useState([]);

  useEffect(() => {
    Promise.all([
      api.get('/api/subjects/').catch(() => ({ data: [] })),
      api.get('/api/themes/').catch(() => ({ data: [] })),
      api.get('/api/generations/batches/').catch(() => ({ data: [] })),
    ]).then(([sRes, tRes, bRes]) => {
      setCounts({
        subjects: sRes.data.length,
        themes: tRes.data.length,
        batches: bRes.data.length,
      });
      setRecentBatches(bRes.data.slice(0, 5));
    });
  }, []);

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-4">
        <div>
          <h2 className="mb-1">Hi {firstname || 'there'} 👋</h2>
          <p className="text-muted mb-0">{organizationStatus.organizationName}</p>
        </div>
        <Link to="/generate" className="btn btn-primary d-flex align-items-center gap-2">
          <Sparkles size={16} /> Generate videos
        </Link>
      </div>

      <div className="row g-3 mb-4">
        <StatCard to="/subjects" icon={<PawPrint />} label="Pets" value={counts.subjects} />
        <StatCard to="/themes" icon={<Palette />} label="Themes" value={counts.themes} />
        <StatCard to="/generations" icon={<Film />} label="Batches" value={counts.batches} />
        {organizationStatus.quota && (
          <StatCard
            to="/generate"
            icon={<Sparkles />}
            label="Videos this month"
            value={`${organizationStatus.quota.used}/${organizationStatus.quota.quota}`}
          />
        )}
      </div>

      <div className="critter-card mb-3">
        <div className="d-flex justify-content-between align-items-center mb-3">
          <h5 className="mb-0">Recent batches</h5>
          <Link to="/generations" className="small">View all →</Link>
        </div>
        {recentBatches.length === 0 && (
          <div className="critter-empty-state">
            <p>No generations yet.</p>
            <Link to="/subjects" className="btn btn-outline-primary btn-sm">
              <Plus size={14} className="me-1" /> Add your first pet
            </Link>
          </div>
        )}
        {recentBatches.map((b) => (
          <Link
            key={b.uuid}
            to={`/generations/${b.uuid}`}
            className="d-flex justify-content-between align-items-center p-2 rounded mb-1"
            style={{ textDecoration: 'none', color: 'inherit', background: '#f8fafc' }}
          >
            <div>
              <div className="fw-semibold">{b.subject_name} — {b.theme_name}</div>
              <small className="text-muted">{new Date(b.created_at).toLocaleString()}</small>
            </div>
            <div>
              <StatusPill status={b.status} />
              <small className="text-muted ms-2">{b.succeeded_count}/{b.total_count} done</small>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

function StatCard({ to, icon, label, value }) {
  return (
    <div className="col-6 col-md-3">
      <Link to={to} className="critter-card critter-card-hover d-block text-decoration-none">
        <div className="d-flex align-items-center gap-3">
          <div className="text-primary">{icon}</div>
          <div>
            <div className="text-muted small">{label}</div>
            <div className="fs-4 fw-semibold">{value}</div>
          </div>
        </div>
      </Link>
    </div>
  );
}

export function StatusPill({ status }) {
  const colorMap = {
    pending: 'secondary',
    running: 'info',
    succeeded: 'success',
    failed: 'danger',
    cancelled: 'warning',
  };
  return (
    <span className={`badge bg-${colorMap[status] || 'secondary'}`}>{status}</span>
  );
}
