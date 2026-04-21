import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import api from '../api';

export default function ForgotPasswordPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [usernameOrEmail, setUsernameOrEmail] = useState('');
  const [resetSessionId, setResetSessionId] = useState('');
  const [code, setCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const onInitiate = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await api.post('/api/users/auth/forgot-password/', { username_or_email: usernameOrEmail });
      setResetSessionId(res.data.reset_session_id);
      setStep(2);
      toast.info('If an account exists, a reset code has been sent.');
    } catch (err) {
      toast.error(err.response?.data?.error || 'Request failed');
    }
    setLoading(false);
  };

  const onVerify = async (e) => {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      toast.error('Passwords do not match');
      return;
    }
    setLoading(true);
    try {
      await api.post('/api/users/auth/verify-password-reset/', {
        reset_session_id: resetSessionId,
        verification_code: code,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      toast.success('Password reset! Sign in with your new password.');
      navigate('/login');
    } catch (err) {
      toast.error(err.response?.data?.error || 'Reset failed');
    }
    setLoading(false);
  };

  return (
    <div className="d-flex align-items-center justify-content-center" style={{ minHeight: '100vh', background: '#f1f5f9' }}>
      <div className="critter-card" style={{ maxWidth: 420, width: '100%' }}>
        <h4 className="mb-3">Reset password</h4>
        {step === 1 && (
          <form onSubmit={onInitiate}>
            <div className="mb-3">
              <label className="form-label small">Username or email</label>
              <input className="form-control" required autoFocus
                     value={usernameOrEmail} onChange={(e) => setUsernameOrEmail(e.target.value)} />
            </div>
            <button type="submit" className="btn btn-primary w-100" disabled={loading}>
              {loading ? 'Sending…' : 'Send reset code'}
            </button>
            <div className="text-center mt-3">
              <Link to="/login" className="small">Back to sign in</Link>
            </div>
          </form>
        )}
        {step === 2 && (
          <form onSubmit={onVerify}>
            <p className="small text-muted">Check your email for the 8-digit reset code.</p>
            <div className="mb-3">
              <label className="form-label small">Reset code</label>
              <input className="form-control" required maxLength={10} value={code} onChange={(e) => setCode(e.target.value)} />
            </div>
            <div className="mb-3">
              <label className="form-label small">New password</label>
              <input type="password" className="form-control" required minLength={8} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
            </div>
            <div className="mb-3">
              <label className="form-label small">Confirm new password</label>
              <input type="password" className="form-control" required minLength={8} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
            </div>
            <button type="submit" className="btn btn-primary w-100" disabled={loading}>
              {loading ? 'Resetting…' : 'Reset password'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
