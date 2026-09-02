import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import GroupDetailModal from '../components/ta/GroupDetailModal.jsx';
import * as adminApi from '../api/admin.js';
import * as sectionsApi from '../api/sections.js';
import * as taApi from '../api/ta.js';
import { usePolling } from '../hooks/usePolling.js';

const STATUS_LABEL = { on_pace: 'on pace', stuck: 'stuck', done: 'done', empty: 'no one here' };
const STATUS_CLASS = {
  on_pace: 'panel-success',
  stuck: 'panel-warning',
  done: 'panel-default',
  empty: 'panel-default',
};

function ratingColor(value) {
  if (value === null || value === undefined) return '#ccc';
  if (value <= 2) return '#d9534f';
  if (value === 3) return '#f0ad4e';
  return '#5cb85c';
}

function NumberTile({ tile, onClick }) {
  const pct =
    tile.total_questions > 0 ? Math.round((tile.current_question_index / tile.total_questions) * 100) : 0;
  const clickable = tile.group_id != null;
  return (
    <div
      className={`panel ${clickable ? 'panel-clickable' : ''} ${STATUS_CLASS[tile.status] || ''}`}
      onClick={clickable ? onClick : undefined}
      style={clickable ? undefined : { opacity: 0.75 }}
    >
      <div className="panel-heading">
        <h4>
          #{tile.number}
          {tile.name && tile.name !== `Group ${tile.number}` ? ` · ${tile.name}` : ''}
        </h4>
        <span className="badge badge-default" style={{ background: 'rgba(255,255,255,0.3)', color: 'inherit' }}>
          {STATUS_LABEL[tile.status] || tile.status}
        </span>
      </div>
      <div className="panel-body">
        {tile.group_id == null ? (
          <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)' }}>Nobody has entered this number yet.</p>
        ) : (
          <>
            <div className="progress" style={{ marginBottom: 10 }}>
              <div
                className={`progress-bar ${tile.status === 'stuck' ? 'progress-bar-warning' : 'progress-bar-success'}`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <div className="group-tile-typist-row">
              <span>Question</span>
              <b>
                {Math.min(tile.current_question_index + 1, tile.total_questions)} of {tile.total_questions}
              </b>
            </div>
            <div className="group-tile-typist-row">
              <span>Logged in</span>
              <b>{tile.present.length > 0 ? tile.present.join(', ') : '—'}</b>
            </div>
            <div className="group-tile-typist-row">
              <span>Typist</span>
              <b>{tile.typist_name || '—'}</b>
            </div>
            <div className="rating-dots">
              {tile.members.map((m) => (
                <div
                  key={m.user_id}
                  className="d"
                  style={{ background: ratingColor(m.rating) }}
                  title={m.display_name}
                >
                  {m.rating ?? '–'}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function TaDashboardPage() {
  const { worksheetId } = useParams();
  const navigate = useNavigate();
  const [selectedGroupId, setSelectedGroupId] = useState(null);
  const [classId, setClassId] = useState(null);
  const [watched, setWatched] = useState([]);
  const [addNumber, setAddNumber] = useState('');
  const [watchError, setWatchError] = useState('');

  useEffect(() => {
    adminApi
      .getWorksheet(worksheetId)
      .then((res) => {
        setClassId(res.worksheet.class_id);
        return sectionsApi.getWatchedNumbers(res.worksheet.class_id);
      })
      .then((res) => setWatched(res.numbers))
      .catch((err) => setWatchError(err.message));
  }, [worksheetId]);

  const saveWatched = async (next) => {
    setWatchError('');
    const prev = watched;
    setWatched(next);
    try {
      const res = await sectionsApi.setWatchedNumbers(classId, next);
      setWatched(res.numbers);
    } catch (err) {
      setWatchError(err.message);
      setWatched(prev);
    }
  };

  const removeNumber = (n) => saveWatched(watched.filter((x) => x !== n));
  const handleAddNumber = (e) => {
    e.preventDefault();
    const n = Number(addNumber);
    if (!n || watched.includes(n)) {
      setAddNumber('');
      return;
    }
    saveWatched([...watched, n].sort((a, b) => a - b));
    setAddNumber('');
  };

  const fetchDashboard = useCallback((signal) => taApi.getDashboard(worksheetId, signal), [worksheetId]);
  const { data, error, loading } = usePolling(fetchDashboard, { intervalMs: 3000 });

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
        <div>
          <h1>Live section view</h1>
          <p>Watching the group numbers below · click a group for detail · updates as students work</p>
        </div>
      </div>

      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-body">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 13, color: 'var(--muted)' }}>Watching:</span>
            {watched.map((n) => (
              <span
                key={n}
                className="badge badge-default"
                style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
              >
                #{n}
                <button
                  type="button"
                  onClick={() => removeNumber(n)}
                  style={{ border: 'none', background: 'none', cursor: 'pointer', padding: 0, lineHeight: 1 }}
                  title="Stop watching"
                >
                  ✕
                </button>
              </span>
            ))}
            {watched.length === 0 && <span style={{ fontSize: 13, color: 'var(--muted)' }}>none yet</span>}
            <form onSubmit={handleAddNumber} style={{ display: 'inline-flex', gap: 6, marginLeft: 8 }}>
              <input
                type="number"
                min="1"
                className="form-control"
                style={{ width: 90 }}
                value={addNumber}
                onChange={(e) => setAddNumber(e.target.value)}
                placeholder="add #"
              />
              <button className="btn btn-sm" type="submit" disabled={!addNumber}>
                Add
              </button>
            </form>
          </div>
          {watchError && <p style={{ color: 'var(--danger, #d9534f)', fontSize: 13, margin: '8px 0 0' }}>{watchError}</p>}
        </div>
      </div>

      {error && (
        <div className="alert alert-danger">
          Lost the connection ({error.message}) — still retrying every few seconds.
        </div>
      )}
      {loading && !data ? (
        <div className="page-loading">Loading…</div>
      ) : (
        <div className="card-holder">
          {(data?.groups || []).map((tile) => (
            <NumberTile
              key={tile.number}
              tile={tile}
              onClick={() => tile.group_id != null && setSelectedGroupId(tile.group_id)}
            />
          ))}
          {(data?.groups || []).length === 0 && (
            <p style={{ color: 'var(--muted)' }}>Add a group number above to start watching.</p>
          )}
        </div>
      )}

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
