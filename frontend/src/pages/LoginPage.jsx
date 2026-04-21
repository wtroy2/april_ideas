import { useState, useContext } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import { Sparkles } from 'lucide-react';
import api from '../api';
import tokenManager from '../utils/TokenManager';
import { AuthContext } from '../context/AuthContext';

export default function LoginPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const redirectTo = params.get('redirect') || '/';
  const sessionExpired = params.get('reason') === 'session_expired';

  const { setIsAuthenticated, fetchUsername, checkOrganizationStatus } = useContext(AuthContext);

  // Step 1 (credentials) → Step 2 (2FA code)
  const [step, setStep] = useState(1);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [loginSessionId, setLoginSessionId] = useState('');
  const [emailHint, setEmailHint] = useState('');
  const [loading, setLoading] = useState(false);

  const onCredentialsSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await api.post('/api/users/auth/initiate-login/', { username, password });

      // Backend returned tokens directly (REQUIRE_2FA=False on the server) —
      // single-step login, skip the code prompt.
      if (res.data.access && res.data.refresh) {
        tokenManager.setTokens(res.data.access, res.data.refresh);
        setIsAuthenticated(true);
        await fetchUsername();
        await checkOrganizationStatus();
        toast.success('Welcome back!');
        navigate(redirectTo, { replace: true });
        return;
      }

      // Otherwise: 2FA flow — go to step 2
      setLoginSessionId(res.data.login_session_id);
      setEmailHint(res.data.email_hint || '');
      setStep(2);
      toast.info(`Verification code sent to ${res.data.email_hint || 'your email'}`);
    } catch (err) {
      toast.error(err.response?.data?.error || 'Login failed');
    }
    setLoading(false);
  };

  const onCodeSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await api.post('/api/users/auth/verify-login/', {
        login_session_id: loginSessionId,
        verification_code: code,
      });
      tokenManager.setTokens(res.data.access, res.data.refresh);
      setIsAuthenticated(true);
      await fetchUsername();
      await checkOrganizationStatus();
      toast.success('Welcome back!');
      navigate(redirectTo, { replace: true });
    } catch (err) {
      toast.error(err.response?.data?.error || 'Invalid code');
    }
    setLoading(false);
  };

  const onResend = async () => {
    setLoading(true);
    try {
      await api.post('/api/users/auth/resend-code/', { login_session_id: loginSessionId });
      toast.info('New code sent');
    } catch (err) {
      toast.error(err.response?.data?.error || 'Could not resend');
    }
    setLoading(false);
  };

  return (
    <div className="d-flex align-items-center justify-content-center" style={{ minHeight: '100vh', background: '#f1f5f9' }}>
      <div className="critter-card" style={{ maxWidth: 420, width: '100%' }}>
        <div className="text-center mb-4">
          <Sparkles size={32} className="text-primary mb-2" />
          <h3 className="mb-1">Welcome to Critter</h3>
          <p className="text-muted small mb-0">AI video for pet creators</p>
        </div>

        {sessionExpired && (
          <div className="alert alert-warning small">Your session expired. Please sign in again.</div>
        )}

        {step === 1 && (
          <form onSubmit={onCredentialsSubmit}>
            <div className="mb-3">
              <label className="form-label small">Username or email</label>
              <input
                type="text" className="form-control" required autoFocus
                value={username} onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div className="mb-3">
              <label className="form-label small">Password</label>
              <input
                type="password" className="form-control" required
                value={password} onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <button type="submit" className="btn btn-primary w-100" disabled={loading}>
              {loading ? 'Signing in…' : 'Continue'}
            </button>
            <div className="d-flex justify-content-between mt-3">
              <Link to="/forgot-password" className="small">Forgot password?</Link>
              <Link to="/register" className="small">Create account</Link>
            </div>
          </form>
        )}

        {step === 2 && (
          <form onSubmit={onCodeSubmit}>
            <p className="small text-muted mb-3">
              Enter the 6-digit code sent to <strong>{emailHint}</strong>.
            </p>
            <div className="mb-3">
              <input
                type="text"
                className="form-control text-center"
                style={{ fontSize: 24, letterSpacing: 8 }}
                maxLength={6} required autoFocus inputMode="numeric"
                value={code} onChange={(e) => setCode(e.target.value)}
              />
            </div>
            <button type="submit" className="btn btn-primary w-100" disabled={loading}>
              {loading ? 'Verifying…' : 'Sign in'}
            </button>
            <div className="d-flex justify-content-between mt-3">
              <button type="button" className="btn btn-link p-0 small" onClick={() => setStep(1)}>
                ← Back
              </button>
              <button type="button" className="btn btn-link p-0 small" onClick={onResend} disabled={loading}>
                Resend code
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
