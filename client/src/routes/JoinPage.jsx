import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import * as wApi from '../api/w.js';

/** The student landing page for a share link (/w/:code). No login — type a
 * name and a group number and go. Identity is a signed-cookie participant
 * key minted by the join call. */
export default function JoinPage() {
  const { code } = useParams();
  const navigate = useNavigate();

  const [info, setInfo] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [name, setName] = useState('');
  const [number, setNumber] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    wApi
      .resolve(code)
      .then((res) => {
        setInfo(res);
        if (res.my_name) setName(res.my_name);
      })
      .catch((err) => setLoadError(err.message));
  }, [code]);

  const go = (groupId) => navigate(`/w/${code}/g/${groupId}`);

  const submit = async (mode) => {
    setError('');
    setBusy(true);
    try {
      const res =
        mode === 'solo'
          ? await wApi.workIndividually(code, { name: name.trim() })
          : await wApi.join(code, { name: name.trim(), number: Number(number) });
      go(res.group_id);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  if (loadError) {
    return (
      <div style={wrap}>
        <div className="panel">
          <div className="panel-body">
            <h3>That link didn’t work</h3>
            <p style={{ color: 'var(--muted)' }}>{loadError}</p>
          </div>
        </div>
      </div>
    );
  }
  if (!info) return <div className="page-loading">Loading…</div>;

  return (
    <div style={wrap}>
      <div className="panel">
        <div className="panel-heading">
          <h3 style={{ margin: 0 }}>{info.worksheet_title}</h3>
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>{info.class_name}</span>
        </div>
        <div className="panel-body">
          {info.resumable_group_id && (
            <button
              className="btn btn-primary"
              style={{ marginBottom: 14 }}
              onClick={() => go(info.resumable_group_id)}
            >
              Resume where you left off
            </button>
          )}
          <div className="form-group">
            <label htmlFor="jp-name">Your name</label>
            <input
              id="jp-name"
              className="form-control"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="First name is fine"
              autoFocus
            />
          </div>
          <div className="form-group">
            <label htmlFor="jp-number">Group number</label>
            <input
              id="jp-number"
              className="form-control"
              style={{ maxWidth: 140 }}
              inputMode="numeric"
              value={number}
              onChange={(e) => setNumber(e.target.value.replace(/\D/g, ''))}
              placeholder="e.g. 3"
            />
            <p style={{ fontSize: 12, color: 'var(--muted)', margin: '4px 0 0' }}>
              Everyone who types the same number is in the same group.
            </p>
          </div>
          {error && <div className="alert alert-danger">{error}</div>}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 6 }}>
            <button
              className="btn btn-primary"
              disabled={busy || !name.trim() || !number}
              onClick={() => submit('group')}
            >
              {busy ? 'Joining…' : 'Join group'}
            </button>
            <button className="btn" disabled={busy || !name.trim()} onClick={() => submit('solo')}>
              Work individually
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

const wrap = { maxWidth: 460, margin: '48px auto', padding: '0 16px' };
