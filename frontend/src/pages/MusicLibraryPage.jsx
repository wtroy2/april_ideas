import { useEffect, useState, useRef } from 'react';
import { Music, Upload, Trash2, Volume2 } from 'lucide-react';
import { toast } from 'react-toastify';
import api from '../api';

export default function MusicLibraryPage() {
  const [tracks, setTracks] = useState([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);

  const refresh = () => api.get('/api/assets/audio/').then((r) => setTracks(r.data));
  useEffect(refresh, []);

  const onUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith('audio/')) {
      toast.error(`Not an audio file: ${file.type}`);
      return;
    }
    const data = new FormData();
    data.append('audio', file);
    setUploading(true);
    try {
      await api.post('/api/assets/audio/upload/', data, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      toast.success(`Uploaded ${file.name}`);
      refresh();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Upload failed');
    }
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const onDelete = async (uuid) => {
    if (!confirm('Delete this track?')) return;
    await api.delete(`/api/assets/${uuid}/delete/`);
    refresh();
  };

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-4">
        <div>
          <h2 className="mb-1">Music library</h2>
          <p className="text-muted mb-0">Tracks you can overlay on generated videos</p>
        </div>
        <label className="btn btn-primary d-flex align-items-center gap-2 mb-0">
          <Upload size={16} /> {uploading ? 'Uploading…' : 'Upload track'}
          <input
            ref={fileInputRef}
            type="file" accept="audio/*" hidden
            onChange={onUpload} disabled={uploading}
          />
        </label>
      </div>

      {tracks.length === 0 ? (
        <div className="critter-card critter-empty-state">
          <Music size={36} className="text-muted mb-2" />
          <h5>No tracks yet</h5>
          <p className="text-muted mb-3">Upload an mp3 or m4a to use as background music in your videos.</p>
        </div>
      ) : (
        <div className="critter-card p-0">
          <table className="table mb-0 align-middle">
            <thead>
              <tr>
                <th>Track</th>
                <th>Size</th>
                <th>Uploaded</th>
                <th>Preview</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {tracks.map((t) => (
                <tr key={t.uuid}>
                  <td>
                    <Volume2 size={14} className="text-muted me-1" />
                    {t.original_filename || t.uuid.slice(0, 8)}
                  </td>
                  <td><small className="text-muted">{(t.size_bytes / 1024 / 1024).toFixed(1)} MB</small></td>
                  <td><small className="text-muted">{new Date(t.created_at).toLocaleDateString()}</small></td>
                  <td style={{ width: 250 }}>
                    {t.signed_url && (
                      <audio controls src={t.signed_url} style={{ height: 28, width: '100%' }} preload="none" />
                    )}
                  </td>
                  <td>
                    <button onClick={() => onDelete(t.uuid)} className="btn btn-sm btn-outline-danger">
                      <Trash2 size={12} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
