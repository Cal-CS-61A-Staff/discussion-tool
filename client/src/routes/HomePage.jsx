import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import SectionCard from '../components/home/SectionCard.jsx';
import * as sectionsApi from '../api/sections.js';
import { useAuth } from '../context/AuthContext.jsx';
import { isStaff } from '../utils/roles.js';

export default function HomePage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [sections, setSections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    sectionsApi
      .listSections()
      .then((res) => {
        if (!cancelled) setSections(res.sections);
      })
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) return <div className="page-loading">Loading…</div>;

  return (
    <div>
      <div className="jumbotron">
        <div>
          <h1>CS 61A Discussion</h1>
          <p>
            Welcome, {user.display_name}.{' '}
            {isStaff(user)
              ? 'Pick a class below to manage its assignments and groups.'
              : 'Pick your class below to see its assignments.'}
          </p>
        </div>
      </div>

      <div className="page-header-row">
        <h1>Classes</h1>
      </div>
      {error && <div className="alert alert-danger">Couldn&apos;t load your classes: {error}</div>}
      <div className="card-holder">
        {sections.map((s) => (
          <SectionCard key={s.id} section={s} onClick={() => navigate(`/classes/${s.id}`)} />
        ))}
        {!error && sections.length === 0 && <p style={{ color: 'var(--muted)' }}>No classes yet.</p>}
      </div>
    </div>
  );
}
