import { useEffect, useState } from 'react';
import * as groupsApi from '../../api/groups.js';

const STATUS_LABEL = {
  completed: { label: 'Completed', className: 'badge-success' },
  in_progress: { label: 'In progress', className: 'badge-warning' },
  not_started: { label: 'Not started', className: 'badge-default' },
};

export default function GroupHistoryPanel({ groupId }) {
  const [history, setHistory] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    groupsApi
      .getGroupHistory(groupId)
      .then((data) => setHistory(data.history))
      .catch((err) => setError(err.message));
  }, [groupId]);

  if (error) return <div className="alert alert-danger">{error}</div>;
  if (!history) return <p style={{ color: 'var(--muted)' }}>Loading…</p>;

  return (
    <div className="table-wrap">
      <table className="admin-table">
        <thead>
          <tr>
            <th>Discussion</th>
            <th>Status</th>
            <th>Progress</th>
          </tr>
        </thead>
        <tbody>
          {history.map((h) => {
            const status = STATUS_LABEL[h.status] || STATUS_LABEL.not_started;
            return (
              <tr key={h.worksheet_id}>
                <td>{h.title}</td>
                <td>
                  <span className={`badge ${status.className}`}>{status.label}</span>
                </td>
                <td>
                  {h.questions_completed} / {h.total_questions}
                </td>
              </tr>
            );
          })}
          {history.length === 0 && (
            <tr>
              <td colSpan={3} style={{ color: 'var(--muted)', textAlign: 'center', padding: 20 }}>
                No discussions released in this class yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
