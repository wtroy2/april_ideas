import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Film } from 'lucide-react';
import api from '../api';
import { StatusPill } from './DashboardPage';

export default function StoryListPage() {
  const [stories, setStories] = useState([]);

  useEffect(() => {
    api.get('/api/stories/').then((r) => setStories(r.data));
  }, []);

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-4">
        <div>
          <h2 className="mb-1">Long-form stories</h2>
          <p className="text-muted mb-0">Multi-scene videos stitched from individual AI clips</p>
        </div>
        <Link to="/stories/new" className="btn btn-primary d-flex align-items-center gap-2">
          <Plus size={16} /> New story
        </Link>
      </div>

      {stories.length === 0 ? (
        <div className="critter-card critter-empty-state">
          <Film size={36} className="text-muted mb-2" />
          <h5>No stories yet</h5>
          <p className="text-muted mb-3">
            Plan a longer video — Claude breaks your concept into scenes, you review + edit,
            we generate N takes per scene, you pick favorites, we stitch them together.
          </p>
          <Link to="/stories/new" className="btn btn-primary">
            <Plus size={16} className="me-1" /> Start a story
          </Link>
        </div>
      ) : (
        <div className="critter-card p-0">
          <table className="table mb-0 align-middle">
            <thead>
              <tr>
                <th>Title</th>
                <th>Subject</th>
                <th>Length</th>
                <th>Scenes</th>
                <th>Status</th>
                <th>Updated</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {stories.map((s) => (
                <tr key={s.uuid}>
                  <td>{s.title || <em className="text-muted">Untitled</em>}</td>
                  <td>{s.subject_name}</td>
                  <td>{s.total_duration_seconds}s / {s.target_duration_seconds}s target</td>
                  <td>{s.scenes.length}</td>
                  <td><StatusPill status={s.status.replace('_', ' ')} /></td>
                  <td><small className="text-muted">{new Date(s.updated_at).toLocaleString()}</small></td>
                  <td><Link to={`/stories/${s.uuid}`} className="small">Open →</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
