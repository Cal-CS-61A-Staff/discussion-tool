import { useEffect, useState } from 'react';
import * as sectionsApi from '../../api/sections.js';

export default function SectionGroupsPanel({ sectionId }) {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [addCount, setAddCount] = useState(1);
  const [editingId, setEditingId] = useState(null);
  const [editingName, setEditingName] = useState('');
  const [busyGroupId, setBusyGroupId] = useState(null);
  const [adding, setAdding] = useState(false);

  const load = () => {
    setLoading(true);
    sectionsApi
      .sectionProgress(sectionId)
      .then((data) => setGroups(data.groups))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sectionId]);

  const handleAdd = async (e) => {
    e.preventDefault();
    setError('');
    setAdding(true);
    try {
      await sectionsApi.createGroups(sectionId, Number(addCount) || 1);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setAdding(false);
    }
  };

  const startEdit = (group) => {
    setEditingId(group.group_id);
    setEditingName(group.name);
  };

  const saveEdit = async (groupId) => {
    setBusyGroupId(groupId);
    setError('');
    try {
      await sectionsApi.renameGroup(groupId, editingName.trim());
      setEditingId(null);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyGroupId(null);
    }
  };

  const handleDelete = async (group) => {
    if (!window.confirm(`Delete Group ${group.number} (${group.name})? This removes all its members' progress.`)) {
      return;
    }
    setBusyGroupId(group.group_id);
    setError('');
    try {
      await sectionsApi.deleteGroup(group.group_id);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyGroupId(null);
    }
  };

  if (loading) return <p style={{ color: 'var(--muted)' }}>Loading…</p>;

  return (
    <div>
      {error && <div className="alert alert-danger">{error}</div>}

      <div className="table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Group #</th>
              <th>Name</th>
              <th>Members</th>
              <th>Assignments completed</th>
              <th>Avg. confidence</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((g) => {
              const editing = editingId === g.group_id;
              const busy = busyGroupId === g.group_id;
              return (
                <tr key={g.group_id}>
                  <td>{g.number}</td>
                  <td>
                    {editing ? (
                      <input
                        className="form-control"
                        value={editingName}
                        onChange={(e) => setEditingName(e.target.value)}
                        autoFocus
                      />
                    ) : (
                      g.name
                    )}
                  </td>
                  <td>
                    {g.member_names.length > 0 ? (
                      g.member_names.join(', ')
                    ) : (
                      <span style={{ color: 'var(--muted)' }}>empty</span>
                    )}
                  </td>
                  <td>
                    {g.assignments_completed} / {g.total_assignments}
                  </td>
                  <td>{g.average_rating != null ? `${g.average_rating} / 5` : '—'}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {editing ? (
                      <>
                        <a
                          href="/"
                          className="admin-action"
                          onClick={(e) => {
                            e.preventDefault();
                            if (!busy) saveEdit(g.group_id);
                          }}
                        >
                          {busy ? 'Saving…' : 'Save'}
                        </a>
                        <a
                          href="/"
                          className="admin-action"
                          onClick={(e) => {
                            e.preventDefault();
                            setEditingId(null);
                          }}
                        >
                          Cancel
                        </a>
                      </>
                    ) : (
                      <a
                        href="/"
                        className="admin-action"
                        onClick={(e) => {
                          e.preventDefault();
                          startEdit(g);
                        }}
                      >
                        Edit
                      </a>
                    )}
                    <a
                      href="/"
                      className="admin-action admin-action-danger"
                      onClick={(e) => {
                        e.preventDefault();
                        if (!busy) handleDelete(g);
                      }}
                    >
                      {busy ? 'Deleting…' : 'Delete'}
                    </a>
                  </td>
                </tr>
              );
            })}
            {groups.length === 0 && (
              <tr>
                <td colSpan={6} style={{ color: 'var(--muted)', textAlign: 'center', padding: 20 }}>
                  No groups yet — add some below.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <form onSubmit={handleAdd} style={{ marginTop: 12, display: 'flex', gap: 8, alignItems: 'flex-end' }}>
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label htmlFor={`addCount-${sectionId}`}>Add groups</label>
          <input
            id={`addCount-${sectionId}`}
            type="number"
            min="1"
            max="50"
            className="form-control"
            style={{ width: 100 }}
            value={addCount}
            onChange={(e) => setAddCount(e.target.value)}
          />
        </div>
        <button className="btn btn-sm btn-primary" type="submit" disabled={adding}>
          {adding ? 'Adding…' : '+ Add groups'}
        </button>
      </form>
    </div>
  );
}
