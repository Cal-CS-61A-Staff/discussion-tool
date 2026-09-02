import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import * as authApi from '../api/auth.js';
import { useAuth } from '../context/AuthContext.jsx';

export default function LoginPage() {
  const { login, adminLogin } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const [showAdminLogin, setShowAdminLogin] = useState(false);
  const [adminId, setAdminId] = useState('');
  const [adminError, setAdminError] = useState('');
  const [adminSubmitting, setAdminSubmitting] = useState(false);

  const [authConfig, setAuthConfig] = useState(null);

  useEffect(() => {
    authApi
      .getAuthConfig()
      .then(setAuthConfig)
      .catch(() => setAuthConfig({ google_enabled: false, passwordless_enabled: true }));

    if (new URLSearchParams(location.search).get('error') === 'domain_not_allowed') {
      setError('Sign-in is restricted to berkeley.edu accounts.');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await login(displayName.trim(), 'student', email.trim());
      const dest = location.state?.from || '/';
      navigate(dest, { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleAdminSubmit = async (e) => {
    e.preventDefault();
    setAdminError('');
    setAdminSubmitting(true);
    try {
      await adminLogin(adminId.trim());
      const dest = location.state?.from || '/';
      navigate(dest, { replace: true });
    } catch (err) {
      setAdminError(err.message);
    } finally {
      setAdminSubmitting(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div className="panel" style={{ width: '100%', maxWidth: 380, margin: '0 16px' }}>
        <div className="panel-heading" style={{ background: 'var(--brand)', color: '#fff' }}>
          <h3>CS 61A Discussion</h3>
        </div>
        <div className="panel-body">
          {error && <div className="alert alert-danger">{error}</div>}

          {authConfig?.google_enabled && (
            <a
              href="/api/auth/google/login"
              className="btn btn-block"
              style={{ marginBottom: 16, textDecoration: 'none' }}
            >
              Sign in with Google
            </a>
          )}

          {authConfig?.passwordless_enabled && (
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label htmlFor="displayName">Display name</label>
                <input
                  id="displayName"
                  className="form-control"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Your name"
                  required
                  autoFocus
                />
              </div>
              <div className="form-group">
                <label htmlFor="email">Email (optional)</label>
                <input
                  id="email"
                  type="email"
                  className="form-control"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@berkeley.edu"
                />
                <p style={{ fontSize: 11, color: 'var(--muted)', margin: '4px 0 0' }}>
                  If your email is on a class roster, it links you to your assigned section and TA automatically.
                </p>
              </div>
              <button type="submit" className="btn btn-gold btn-block" disabled={submitting || !displayName.trim()}>
                {submitting ? 'Signing in…' : 'Sign in'}
              </button>
            </form>
          )}
          {authConfig?.passwordless_enabled && (
            <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 16, marginBottom: 0 }}>
              Prototype sign-in — no password required. Real Canvas/bCourses login can replace this later.
            </p>
          )}

          {authConfig?.passwordless_enabled && (
            <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
              {!showAdminLogin ? (
                <button
                  type="button"
                  className="btn btn-sm"
                  style={{ width: '100%' }}
                  onClick={() => setShowAdminLogin(true)}
                >
                  Sign in as admin
                </button>
              ) : (
                <form onSubmit={handleAdminSubmit}>
                  <div className="form-group" style={{ marginBottom: 8 }}>
                    <label htmlFor="adminId">Admin account id</label>
                    <input
                      id="adminId"
                      className="form-control"
                      value={adminId}
                      onChange={(e) => setAdminId(e.target.value)}
                      placeholder="Created via `flask create-admin`"
                      required
                      autoFocus
                    />
                  </div>
                  {adminError && <div className="alert alert-danger">{adminError}</div>}
                  <button type="submit" className="btn btn-block" disabled={adminSubmitting || !adminId.trim()}>
                    {adminSubmitting ? 'Signing in…' : 'Sign in as admin'}
                  </button>
                </form>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
