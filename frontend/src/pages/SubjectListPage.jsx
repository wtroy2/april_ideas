import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, PawPrint } from 'lucide-react';
import { toast } from 'react-toastify';
import api from '../api';

export default function SubjectListPage() {
  const [subjects, setSubjects] = useState([]);
  const [showNew, setShowNew] = useState(false);
  const [form, setForm] = useState({ name: '', kind: 'pet', species: '' });
  const [loading, setLoading] = useState(false);

  const refresh = () => {
    api.get('/api/subjects/').then((res) => setSubjects(res.data));
  };
  useEffect(refresh, []);

  const onCreate = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await api.post('/api/subjects/create/', form);
      toast.success(`Created ${res.data.name}`);
      setShowNew(false);
      setForm({ name: '', kind: 'pet', species: '' });
      refresh();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Could not create');
    }
    setLoading(false);
  };

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-4">
        <div>
          <h2 className="mb-1">Your pets</h2>
          <p className="text-muted mb-0">Saved characters used in video generation</p>
        </div>
        <button className="btn btn-primary d-flex align-items-center gap-2" onClick={() => setShowNew(true)}>
          <Plus size={16} /> New pet
        </button>
      </div>

      {showNew && (
        <div className="critter-card mb-3">
          <form onSubmit={onCreate} className="row g-2 align-items-end">
            <div className="col-md-4">
              <label className="form-label small">Name</label>
              <input className="form-control" required autoFocus
                     value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div className="col-md-3">
              <label className="form-label small">Kind</label>
              <select className="form-select" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                <option value="pet">Pet</option>
                <option value="person">Person</option>
                <option value="object">Object</option>
              </select>
            </div>
            <div className="col-md-3">
              <label className="form-label small">Species</label>
              <select className="form-select" value={form.species} onChange={(e) => setForm({ ...form, species: e.target.value })}>
                <option value="">—</option>
                <option value="cat">Cat</option>
                <option value="dog">Dog</option>
                <option value="bird">Bird</option>
                <option value="rabbit">Rabbit</option>
                <option value="hamster">Hamster</option>
                <option value="reptile">Reptile</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div className="col-md-2 d-flex gap-1">
              <button type="submit" className="btn btn-primary flex-grow-1" disabled={loading}>Save</button>
              <button type="button" className="btn btn-outline-secondary" onClick={() => setShowNew(false)}>×</button>
            </div>
          </form>
        </div>
      )}

      {subjects.length === 0 ? (
        <div className="critter-card critter-empty-state">
          <PawPrint size={36} className="text-muted mb-2" />
          <h5>No pets yet</h5>
          <p className="text-muted mb-3">Create your first pet profile to start generating videos.</p>
          <button onClick={() => setShowNew(true)} className="btn btn-primary">
            <Plus size={16} className="me-1" /> New pet
          </button>
        </div>
      ) : (
        <div className="row g-3">
          {subjects.map((s) => (
            <div key={s.uuid} className="col-md-4 col-lg-3">
              <Link to={`/subjects/${s.uuid}`} className="critter-card critter-card-hover d-block text-decoration-none text-reset">
                {s.photos?.[0]?.asset?.signed_url ? (
                  <img src={s.photos[0].asset.signed_url} alt="" className="subject-photo-thumb mb-2" />
                ) : (
                  <div className="subject-photo-thumb bg-light d-flex align-items-center justify-content-center mb-2">
                    <PawPrint size={36} className="text-muted" />
                  </div>
                )}
                <div className="fw-semibold">{s.name}</div>
                <small className="text-muted">{s.species || s.kind} · {s.photo_count} photo{s.photo_count === 1 ? '' : 's'}</small>
              </Link>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
