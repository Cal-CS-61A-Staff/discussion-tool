import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import * as sectionsApi from '../api/sections.js';

export default function TaGroupsPage() {
  const { sectionId } = useParams();
  const navigate = useNavigate();
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [addCount, setAddCount] = useState(1);
  const [editingId, setEditingId] = useState(null);
  const [editingName, setEditingName] = useState('');

  const load = () => {
    setLoading(true);
    sectionsApi
      .sectionGroups(sectionId)
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
    try {
      await sectionsApi.createGroups(sectionId, Number(addCount) || 1);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const startEdit = (group) => {
    setEditingId(group.id);
    setEditingName(group.name);
  };

  const saveEdit = async (groupId) => {
    setError('');
    try {
      await sectionsApi.renameGroup(groupId, editingName.trim());
      setEditingId(null);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDelete = async (group) => {
    if (!window.confirm(`Delete Group ${group.number} (${group.name})? This removes all its members' progress.`)) {
      return;
    }
    setError('');
    try {
      await sectionsApi.deleteGroup(group.id);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  if (loading) return <div className="page-loading">Loading…</div>;

  return (
    <div>
      <div className="breadcrumb-row">
        <a
          href="/"
          onClick={(e) => {
            e.preventDefault();
            navigate(`/classes/${sectionId}`);
          }}
        >
          ← Back to class
        </a>
      </div>
      <div className="page-header-row">
        <h1>Manage groups</h1>
        <p>Students join this section by entering the group number below.</p>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Group #</th>
              <th>Name</th>
              <th>Members</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((g) => (
              <tr key={g.id}>
                <td>{g.number}</td>
                <td>
                  {editingId === g.id ? (
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
                  {g.member_count > 0 ? (
                    g.member_names.join(', ')
                  ) : (
                    <span style={{ color: 'var(--muted)' }}>empty</span>
                  )}
                </td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  {editingId === g.id ? (
                    <>
                      <a
                        href="/"
                        className="admin-action"
                        onClick={(e) => {
                          e.preventDefault();
                          saveEdit(g.id);
                        }}
                      >
                        Save
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
                      handleDelete(g);
                    }}
                  >
                    Delete
                  </a>
                </td>
              </tr>
            ))}
            {groups.length === 0 && (
              <tr>
                <td colSpan={4} style={{ color: 'var(--muted)', textAlign: 'center', padding: 20 }}>
                  No groups yet — add some below.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <form onSubmit={handleAdd} style={{ marginTop: 16, display: 'flex', gap: 8, alignItems: 'flex-end' }}>
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label htmlFor="addCount">Add groups</label>
          <input
            id="addCount"
            type="number"
            min="1"
            max="50"
            className="form-control"
            style={{ width: 100 }}
            value={addCount}
            onChange={(e) => setAddCount(e.target.value)}
          />
        </div>
        <button className="btn btn-primary" type="submit">
          + Add groups
        </button>
      </form>
    </div>
  );
}
