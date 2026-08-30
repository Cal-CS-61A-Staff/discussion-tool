import { useCallback, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import GroupDetailModal from '../components/ta/GroupDetailModal.jsx';
import GroupTile from '../components/ta/GroupTile.jsx';
import * as taApi from '../api/ta.js';
import { usePolling } from '../hooks/usePolling.js';

export default function TaDashboardPage() {
  const { worksheetId } = useParams();
  const navigate = useNavigate();
  const [selectedGroupId, setSelectedGroupId] = useState(null);

  const fetchDashboard = useCallback((signal) => taApi.getDashboard(worksheetId, signal), [worksheetId]);
  const { data, error, loading } = usePolling(fetchDashboard, { intervalMs: 3000 });

  if (loading && !data) return <div className="page-loading">Loading…</div>;
  if (error && !data) return <div className="page-loading">Couldn&apos;t load this dashboard: {error.message}</div>;

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
      {error && (
        <div className="alert alert-danger">
          Lost the connection ({error.message}) — still retrying every few seconds. The groups below may be out of
          date until it reconnects.
        </div>
      )}
      <div className="page-header-row">
        <div>
          <h1>Live section view</h1>
          <p>
            {data.groups.length} group{data.groups.length === 1 ? '' : 's'} across every section you're in on this
            class · click a group for detail · updates as students rate each question
          </p>
        </div>
      </div>
      <div className="legend">
        <span>
          <i style={{ background: '#d9534f' }} /> 1–2 low confidence
        </span>
        <span>
          <i style={{ background: '#f0ad4e' }} /> 3 mid
        </span>
        <span>
          <i style={{ background: '#5cb85c' }} /> 4–5 confident
        </span>
      </div>
      <div className="card-holder">
        {data.groups.map((g) => (
          <GroupTile key={g.group_id} group={g} onClick={() => setSelectedGroupId(g.group_id)} />
        ))}
      </div>

      {selectedGroupId && (
        <GroupDetailModal
          groupId={selectedGroupId}
          worksheetId={worksheetId}
          onClose={() => setSelectedGroupId(null)}
        />
      )}
    </div>
  );
}
