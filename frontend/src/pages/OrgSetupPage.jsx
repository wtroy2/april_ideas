import { useState, useContext, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import api from '../api';
import { AuthContext } from '../context/AuthContext';

export default function OrgSetupPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const inviteToken = params.get('invite');
  const { checkOrganizationStatus, organizationStatus } = useContext(AuthContext);

  const [name, setName] = useState('');
  const [orgType, setOrgType] = useState('creator');
  const [loading, setLoading] = useState(false);
  const [invitation, setInvitation] = useState(null);

  // If user already has an org, send them home
  useEffect(() => {
    if (organizationStatus.hasOrganization) navigate('/');
  }, [organizationStatus.hasOrganization, navigate]);

  // If invite token, fetch invitation details
  useEffect(() => {
    if (inviteToken) {
      api.get(`/api/orgs/invitations/${inviteToken}/`)
        .then((res) => setInvitation(res.data))
        .catch(() => toast.error('Invalid or expired invitation'));
    }
  }, [inviteToken]);

  const onCreate = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.post('/api/orgs/create/', { name, org_type: orgType });
      await checkOrganizationStatus();
      toast.success(`Created ${name}`);
      navigate('/');
    } catch (err) {
      toast.error(err.response?.data?.error || 'Could not create organization');
    }
    setLoading(false);
  };

  const onAccept = async () => {
    setLoading(true);
    try {
      await api.post(`/api/orgs/invitations/${inviteToken}/accept/`);
      await checkOrganizationStatus();
      toast.success(`Joined ${invitation.organization_name}`);
      navigate('/');
    } catch (err) {
      toast.error(err.response?.data?.error || 'Could not accept invitation');
    }
    setLoading(false);
  };

  return (
    <div className="d-flex align-items-center justify-content-center" style={{ minHeight: '100vh', background: '#f1f5f9' }}>
      <div className="critter-card" style={{ maxWidth: 460, width: '100%' }}>
        {invitation ? (
          <>
            <h4 className="mb-2">You're invited!</h4>
            <p className="text-muted">
              <strong>{invitation.inviter_name}</strong> invited you to join{' '}
              <strong>{invitation.organization_name}</strong> as a <strong>{invitation.role}</strong>.
            </p>
            <button onClick={onAccept} className="btn btn-primary w-100" disabled={loading}>
              {loading ? 'Joining…' : 'Accept invitation'}
            </button>
          </>
        ) : (
          <>
            <h4 className="mb-3">Set up your workspace</h4>
            <p className="text-muted small">An organization holds your pets, themes, and generations.</p>
            <form onSubmit={onCreate}>
              <div className="mb-3">
                <label className="form-label small">Organization name</label>
                <input className="form-control" required autoFocus
                       value={name} onChange={(e) => setName(e.target.value)}
                       placeholder="e.g. Whiskers HQ" />
              </div>
              <div className="mb-3">
                <label className="form-label small">Type</label>
                <select className="form-select" value={orgType} onChange={(e) => setOrgType(e.target.value)}>
                  <option value="creator">Solo creator</option>
                  <option value="agency">Agency / team</option>
                </select>
              </div>
              <button type="submit" className="btn btn-primary w-100" disabled={loading}>
                {loading ? 'Creating…' : 'Create workspace'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
