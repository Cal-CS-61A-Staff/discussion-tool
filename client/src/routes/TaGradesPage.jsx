import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import * as adminApi from '../api/admin.js';

export default function TaGradesPage() {
  const { worksheetId } = useParams();
  const navigate = useNavigate();
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    adminApi
      .getGrades(worksheetId)
      .then((data) => setGroups(data.groups))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [worksheetId]);

  if (loading) return <div className="page-loading">Loading…</div>;

  return (
    <div>
      <div className="breadcrumb-row">
        <a
          href="/"
          onClick={(e) => {
            e.preventDefault();
            navigate('/assignments');
          }}
        >
          ← Back to assignments
        </a>
      </div>
      <div className="page-header-row">
        <h1>Grades</h1>
        <p>Each group&apos;s latest test run per question.</p>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Group</th>
              <th>Questions passed</th>
              <th>Questions attempted</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((g) => (
              <tr key={g.group_id}>
                <td>
                  {g.name}
                  {g.is_individual && <span style={{ color: 'var(--muted)', fontSize: 12 }}> (individual)</span>}
                </td>
                <td>
                  {g.questions_passed} / {g.total_questions}
                </td>
                <td>
                  {g.questions_attempted} of {g.total_questions}
                </td>
              </tr>
            ))}
            {groups.length === 0 && (
              <tr>
                <td colSpan={3} style={{ color: 'var(--muted)', textAlign: 'center', padding: 20 }}>
                  No groups yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
