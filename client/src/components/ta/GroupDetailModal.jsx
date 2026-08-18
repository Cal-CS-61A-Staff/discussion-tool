import { useCallback, useState } from 'react';
import * as groupsApi from '../../api/groups.js';
import { usePolling } from '../../hooks/usePolling.js';

export default function GroupDetailModal({ groupId, worksheetId, onClose }) {
  const [releasing, setReleasing] = useState(false);
  const [actionError, setActionError] = useState('');

  const fetchDetail = useCallback(
    (signal) => groupsApi.getGroupDetail(groupId, worksheetId, signal),
    [groupId, worksheetId]
  );
  const { data, loading, refetch } = usePolling(fetchDetail, { intervalMs: 3000, enabled: Boolean(groupId) });

  const handleRelease = async () => {
    setActionError('');
    setReleasing(true);
    try {
      await groupsApi.releaseTypist(groupId, worksheetId);
      await refetch();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setReleasing(false);
    }
  };

  const currentTypist = data?.members?.find((m) => m.is_typist);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="panel-heading" style={{ background: 'var(--brand)', color: '#fff' }}>
          <h3>{data ? data.group.name : 'Group detail'}</h3>
          <button className="modal-close-btn" onClick={onClose}>
            ✕
          </button>
        </div>
        <div className="panel-body">
          {loading && !data && <p>Loading…</p>}
          {data && data.group.completed && <p>This group has finished the worksheet.</p>}

          {data && !data.group.completed && (
            <>
              <div className="q-label">
                Question {data.question.order_index + 1} of {data.total_questions} — {data.question.title}
              </div>
              <p className="q-text">{data.question.prompt}</p>

              <div className="alert alert-info">
                <strong>Expected output</strong>
                <div className="rows">
                  <div className="code">{data.question.expected_output}</div>
                </div>
              </div>

              <div className="q-label">Current code</div>
              <pre className="code-editor-wrap" style={{ padding: 12, color: '#eee', overflowX: 'auto', margin: '0 0 14px' }}>
                <code className="code">{data.code || '(empty)'}</code>
              </pre>

              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: 14,
                  flexWrap: 'wrap',
                  gap: 8,
                }}
              >
                <span style={{ fontSize: 13, color: 'var(--muted)' }}>
                  Typist: <b style={{ color: 'var(--ink)' }}>{currentTypist?.display_name || 'none'}</b>
                  {data.cooldown.active && ` · cooldown: ${data.cooldown.remaining_seconds}s`}
                </span>
                <button
                  className="btn btn-danger btn-sm"
                  onClick={handleRelease}
                  disabled={releasing || !currentTypist}
                >
                  {releasing ? 'Releasing…' : 'Release pen'}
                </button>
              </div>

              {actionError && <div className="alert alert-danger">{actionError}</div>}

              <div className="q-label">Members</div>
              <div className="list-group" style={{ marginBottom: 14 }}>
                {data.members.map((m) => (
                  <div
                    key={m.user_id}
                    className="list-group-item"
                    style={{ display: 'flex', justifyContent: 'space-between' }}
                  >
                    <span>
                      {m.display_name}
                      {m.is_typist ? ' (typist)' : ''}
                    </span>
                    <span>{m.rating ?? '—'}</span>
                  </div>
                ))}
              </div>

              <div className="q-label">Recent attempts</div>
              {data.attempts.length === 0 && (
                <p style={{ color: 'var(--muted)', fontSize: 13 }}>No attempts yet.</p>
              )}
              {data.attempts.length > 0 && (
                <div className="list-group">
                  {data.attempts.map((a, i) => (
                    <div key={i} className="list-group-item">
                      <span
                        className={`badge ${a.is_match ? 'badge-success' : 'badge-danger'}`}
                        style={{ marginRight: 8 }}
                      >
                        {a.is_match ? '✓' : '✗'}
                      </span>
                      <span className="code">{a.prediction}</span> — {a.by}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
