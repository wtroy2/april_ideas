import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Sparkles } from 'lucide-react';
import api from '../api';
import { StatusPill } from './DashboardPage';

export default function GenerationListPage() {
  const [batches, setBatches] = useState([]);

  useEffect(() => {
    api.get('/api/generations/batches/').then((r) => setBatches(r.data));
  }, []);

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-4">
        <div>
          <h2 className="mb-1">Generation history</h2>
          <p className="text-muted mb-0">All your video batches</p>
        </div>
        <Link to="/generate" className="btn btn-primary d-flex align-items-center gap-2">
          <Sparkles size={16} /> New batch
        </Link>
      </div>

      {batches.length === 0 ? (
        <div className="critter-card critter-empty-state">
          <h5>No batches yet</h5>
          <p className="text-muted mb-3">Generate your first video batch.</p>
          <Link to="/generate" className="btn btn-primary">
            <Sparkles size={16} className="me-1" /> Get started
          </Link>
        </div>
      ) : (
        <div className="critter-card p-0">
          <table className="table mb-0">
            <thead>
              <tr>
                <th>Pet</th>
                <th>Theme</th>
                <th>Status</th>
                <th>Progress</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {batches.map((b) => (
                <tr key={b.uuid}>
                  <td>{b.subject_name}</td>
                  <td>{b.theme_name}</td>
                  <td><StatusPill status={b.status} /></td>
                  <td>{b.succeeded_count}/{b.total_count} done{b.failed_count > 0 && ` · ${b.failed_count} failed`}</td>
                  <td><small className="text-muted">{new Date(b.created_at).toLocaleString()}</small></td>
                  <td><Link to={`/generations/${b.uuid}`} className="small">Open →</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
