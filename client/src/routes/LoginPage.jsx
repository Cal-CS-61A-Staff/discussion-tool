import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext.jsx';

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [displayName, setDisplayName] = useState('');
  const [role, setRole] = useState('student');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await login(displayName.trim(), role);
      const dest = location.state?.from || '/';
      navigate(dest, { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div className="panel" style={{ width: '100%', maxWidth: 380, margin: '0 16px' }}>
        <div className="panel-heading" style={{ background: 'var(--brand)', color: '#fff' }}>
          <h3>CS 61A Discussion</h3>
        </div>
        <div className="panel-body">
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
              <label>I am a…</label>
              <div style={{ display: 'flex', gap: 6 }}>
                <button
                  type="button"
                  className={`btn ${role === 'student' ? 'btn-primary' : ''}`}
                  style={{ flex: 1 }}
                  onClick={() => setRole('student')}
                >
                  Student
                </button>
                <button
                  type="button"
                  className={`btn ${role === 'ta' ? 'btn-primary' : ''}`}
                  style={{ flex: 1 }}
                  onClick={() => setRole('ta')}
                >
                  TA / Instructor
                </button>
              </div>
            </div>
            {error && <div className="alert alert-danger">{error}</div>}
            <button type="submit" className="btn btn-gold btn-block" disabled={submitting || !displayName.trim()}>
              {submitting ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
          <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 16, marginBottom: 0 }}>
            Prototype sign-in — no password required. Real Canvas/bCourses login can replace this later.
          </p>
        </div>
      </div>
    </div>
  );
}
