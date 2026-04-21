import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import { Sparkles } from 'lucide-react';
import api from '../api';

export default function RegisterPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const inviteToken = params.get('invite');

  const [form, setForm] = useState({
    username: '', email: '', password: '', first_name: '', last_name: '',
  });
  const [loading, setLoading] = useState(false);

  const update = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const onSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.post('/api/users/register/', form);
      toast.success('Account created — please sign in');
      const next = inviteToken ? `/login?invite=${inviteToken}` : '/login';
      navigate(next);
    } catch (err) {
      const data = err.response?.data;
      const msg = typeof data === 'object'
        ? Object.values(data).flat().join(' ')
        : 'Registration failed';
      toast.error(msg);
    }
    setLoading(false);
  };

  return (
    <div className="d-flex align-items-center justify-content-center" style={{ minHeight: '100vh', background: '#f1f5f9' }}>
      <div className="critter-card" style={{ maxWidth: 480, width: '100%' }}>
        <div className="text-center mb-4">
          <Sparkles size={32} className="text-primary mb-2" />
          <h3 className="mb-1">Create your Critter account</h3>
          {inviteToken && <p className="small text-muted mb-0">You've been invited to join an organization</p>}
        </div>
        <form onSubmit={onSubmit}>
          <div className="row g-2 mb-3">
            <div className="col">
              <label className="form-label small">First name</label>
              <input className="form-control" value={form.first_name} onChange={update('first_name')} />
            </div>
            <div className="col">
              <label className="form-label small">Last name</label>
              <input className="form-control" value={form.last_name} onChange={update('last_name')} />
            </div>
          </div>
          <div className="mb-3">
            <label className="form-label small">Username</label>
            <input className="form-control" required value={form.username} onChange={update('username')} />
          </div>
          <div className="mb-3">
            <label className="form-label small">Email</label>
            <input type="email" className="form-control" required value={form.email} onChange={update('email')} />
          </div>
          <div className="mb-3">
            <label className="form-label small">Password</label>
            <input type="password" className="form-control" required minLength={8} value={form.password} onChange={update('password')} />
            <div className="form-text small">At least 8 characters.</div>
          </div>
          <button type="submit" className="btn btn-primary w-100" disabled={loading}>
            {loading ? 'Creating…' : 'Create account'}
          </button>
          <div className="text-center mt-3">
            <Link to="/login" className="small">Already have an account? Sign in</Link>
          </div>
        </form>
      </div>
    </div>
  );
}
