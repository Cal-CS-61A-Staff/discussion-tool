import { useEffect, useState } from 'react';
import PracticeQuestion from '../components/student/PracticeQuestion.jsx';
import * as groupsApi from '../api/groups.js';
import * as sectionsApi from '../api/sections.js';

export default function HistoryPage() {
  const [assignments, setAssignments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [expandedKey, setExpandedKey] = useState(null);
  const [work, setWork] = useState(null);
  const [workLoading, setWorkLoading] = useState(false);
  const [workError, setWorkError] = useState('');

  useEffect(() => {
    sectionsApi
      .myAssignments()
      .then((data) => setAssignments(data.assignments))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const toggleWork = async (a) => {
    const key = `${a.group_id}-${a.worksheet_id}`;
    if (expandedKey === key) {
      setExpandedKey(null);
      return;
    }
    setExpandedKey(key);
    setWork(null);
    setWorkError('');
    setWorkLoading(true);
    try {
      const data = await groupsApi.getGroupWork(a.group_id, a.worksheet_id);
      setWork(data);
    } catch (err) {
      setWorkError(err.message);
    } finally {
      setWorkLoading(false);
    }
  };

  if (loading) return <div className="page-loading">Loading…</div>;

  return (
    <div>
      <div className="page-header-row">
        <div>
          <h1>History</h1>
          <p>Discussions you've completed, with your own confidence rating and a chance to revisit your work.</p>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {assignments.length === 0 && (
        <p style={{ color: 'var(--muted)' }}>Nothing completed yet — finish a discussion to see it here.</p>
      )}

      {assignments.map((a) => {
        const key = `${a.group_id}-${a.worksheet_id}`;
        const expanded = expandedKey === key;
        return (
          <div className="panel" key={key} style={{ marginBottom: 16 }}>
            <div
              className="panel-heading"
              style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
            >
              <div>
                <h4 style={{ margin: 0 }}>{a.title}</h4>
                <span style={{ fontSize: 12, color: 'var(--muted)' }}>{a.group_name}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase' }}>
                    Your confidence
                  </div>
                  <div style={{ fontSize: 18, fontWeight: 600 }}>
                    {a.my_average_rating != null ? `${a.my_average_rating} / 5` : 'Not rated'}
                  </div>
                </div>
                <button type="button" className="btn btn-sm" onClick={() => toggleWork(a)}>
                  {expanded ? 'Hide work' : 'View work'}
                </button>
              </div>
            </div>
            {expanded && (
              <div className="panel-body">
                {workLoading && <p style={{ color: 'var(--muted)' }}>Loading…</p>}
                {workError && <div className="alert alert-danger">{workError}</div>}
                {work &&
                  work.questions.map((q) => (
                    <PracticeQuestion key={q.question_id} groupId={a.group_id} worksheetId={a.worksheet_id} question={q} />
                  ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
