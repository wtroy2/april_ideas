import { useEffect, useState, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, Upload, Star, Trash2, Sparkles, RefreshCw } from 'lucide-react';
import { toast } from 'react-toastify';
import api from '../api';

export default function SubjectDetailPage() {
  const { uuid } = useParams();
  const navigate = useNavigate();
  const [subject, setSubject] = useState(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);

  const refresh = () => api.get(`/api/subjects/${uuid}/`).then((r) => setSubject(r.data));
  useEffect(() => { refresh(); }, [uuid]);

  const onUpload = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    const data = new FormData();
    files.forEach((f) => data.append('photos', f));
    setUploading(true);
    try {
      await api.post(`/api/subjects/${uuid}/photos/`, data, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      toast.success(`Uploaded ${files.length} photo${files.length === 1 ? '' : 's'}`);
      refresh();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Upload failed');
    }
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const setPrimary = async (photoId) => {
    await api.post(`/api/subjects/${uuid}/photos/${photoId}/primary/`);
    refresh();
  };

  const deletePhoto = async (photoId) => {
    if (!confirm('Delete this photo?')) return;
    await api.delete(`/api/subjects/${uuid}/photos/${photoId}/`);
    refresh();
  };

  const regenerateDescription = async () => {
    await api.post(`/api/subjects/${uuid}/regenerate-description/`);
    toast.info('Regenerating — refresh in a few seconds');
  };

  const deleteSubject = async () => {
    if (!confirm(`Archive ${subject.name}?`)) return;
    await api.delete(`/api/subjects/${uuid}/`);
    toast.success('Archived');
    navigate('/subjects');
  };

  if (!subject) return <div>Loading…</div>;

  return (
    <div>
      <Link to="/subjects" className="small text-muted text-decoration-none d-inline-flex align-items-center gap-1 mb-3">
        <ArrowLeft size={14} /> Back to pets
      </Link>

      <div className="d-flex justify-content-between align-items-center mb-4">
        <div>
          <h2 className="mb-1">{subject.name}</h2>
          <p className="text-muted mb-0">{subject.species || subject.kind} · {subject.photo_count} photo{subject.photo_count === 1 ? '' : 's'}</p>
        </div>
        <div className="d-flex gap-2">
          <Link to={`/generate?subject=${subject.uuid}`} className="btn btn-primary d-flex align-items-center gap-1">
            <Sparkles size={16} /> Generate
          </Link>
          <button onClick={deleteSubject} className="btn btn-outline-danger">Archive</button>
        </div>
      </div>

      <div className="critter-card mb-3">
        <div className="d-flex justify-content-between align-items-center mb-2">
          <h6 className="mb-0">Visual description (used in prompts)</h6>
          <button onClick={regenerateDescription} className="btn btn-sm btn-outline-secondary d-flex align-items-center gap-1">
            <RefreshCw size={12} /> Regenerate
          </button>
        </div>
        <p className="mb-0 text-muted small">
          {subject.auto_description || <em>Will be generated from photos by Gemini Vision in a moment…</em>}
        </p>
      </div>

      <div className="critter-card">
        <div className="d-flex justify-content-between align-items-center mb-3">
          <h6 className="mb-0">Reference photos</h6>
          <label className="btn btn-primary btn-sm d-flex align-items-center gap-1 mb-0">
            <Upload size={14} /> {uploading ? 'Uploading…' : 'Add photos'}
            <input
              ref={fileInputRef}
              type="file" accept="image/*" multiple hidden
              onChange={onUpload} disabled={uploading}
            />
          </label>
        </div>
        {subject.photos?.length ? (
          <div className="row g-2">
            {subject.photos.map((p) => (
              <div key={p.id} className="col-6 col-md-3 col-lg-2 position-relative">
                <img
                  src={p.asset.signed_url || p.asset.public_url}
                  alt=""
                  className={`subject-photo-thumb ${p.is_primary ? 'is-primary' : ''}`}
                />
                <div className="d-flex gap-1 mt-1">
                  <button
                    onClick={() => setPrimary(p.id)}
                    className={`btn btn-sm flex-grow-1 d-flex align-items-center justify-content-center gap-1 ${p.is_primary ? 'btn-primary' : 'btn-outline-secondary'}`}
                    title="Use as the canonical reference"
                  >
                    <Star size={12} /> {p.is_primary ? 'Primary' : 'Set'}
                  </button>
                  <button onClick={() => deletePhoto(p.id)} className="btn btn-sm btn-outline-danger">
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="critter-empty-state">
            <p className="text-muted">Upload 5-10 photos of {subject.name} from different angles for the best results.</p>
          </div>
        )}
      </div>
    </div>
  );
}
