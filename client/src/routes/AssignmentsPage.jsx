import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as adminApi from '../api/admin.js';
import * as sectionsApi from '../api/sections.js';
import { useAuth } from '../context/AuthContext.jsx';
import { isStaff } from '../utils/roles.js';

export default function AssignmentsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [classes, setClasses] = useState([]);
  const [worksheetsByClass, setWorksheetsByClass] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [showNewFormFor, setShowNewFormFor] = useState(null);
  const [newTitle, setNewTitle] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [creating, setCreating] = useState(false);
  const [busyWorksheetId, setBusyWorksheetId] = useState(null);

  const load = () => {
    setLoading(true);
    let fetchedClasses = [];
    sectionsApi
      .listClasses()
      .then((res) => {
        fetchedClasses = res.classes;
        setClasses(res.classes);
        return Promise.all(fetchedClasses.map((c) => sectionsApi.classWorksheets(c.id)));
      })
      .then((results) => {
        const byClass = {};
        results.forEach((res, i) => {
          byClass[fetchedClasses[i].id] = res.worksheets;
        });
        setWorksheetsByClass(byClass);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCreateAssignment = async (e, classId) => {
    e.preventDefault();
    setCreating(true);
    setError('');
    try {
      const res = await adminApi.createWorksheet(classId, {
        title: newTitle.trim(),
        description: newDescription.trim(),
      });
      navigate(`/assignments/${res.worksheet.id}/edit`);
    } catch (err) {
      setError(err.message);
      setCreating(false);
    }
  };

  const handleDelete = async (w) => {
    if (!window.confirm(`Delete "${w.title}"? This removes all its questions and group progress.`)) return;
    setBusyWorksheetId(w.id);
    setError('');
    try {
      await adminApi.deleteWorksheet(w.id);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyWorksheetId(null);
    }
  };

  const handleTogglePublish = async (w) => {
    const verb = w.is_published ? 'unpublish' : 'publish';
    const confirmMessage = w.is_published
      ? `Unpublish "${w.title}"? Students will no longer be able to see or access it.`
      : `Publish "${w.title}"? Students will immediately be able to see and start it.`;
    if (!window.confirm(confirmMessage)) return;
    setBusyWorksheetId(w.id);
    setError('');
    try {
      if (verb === 'unpublish') await adminApi.unpublishWorksheet(w.id);
      else await adminApi.publishWorksheet(w.id);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyWorksheetId(null);
    }
  };

  if (!isStaff(user)) {
    return (
      <div className="panel">
        <div className="panel-body">TA or admin access required.</div>
      </div>
    );
  }

  if (loading) return <div className="page-loading">Loading…</div>;

  return (
    <div>
      <div className="page-header-row">
        <div>
          <h1>Assignments</h1>
          <p>Shared across every section of a class — any TA on that class's staff can edit them.</p>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {classes.length === 0 && (
        <p style={{ color: 'var(--muted)' }}>
          You don't own or co-teach any sections yet — assignments live under a class once you do.
        </p>
      )}

      {classes.map((c) => {
        const worksheets = worksheetsByClass[c.id] || [];
        const showNewForm = showNewFormFor === c.id;
        return (
          <div key={c.id} style={{ marginBottom: 32 }}>
            <h3 style={{ marginBottom: 10 }}>{c.course_name}</h3>
            <div className="table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Problem Set Name</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {worksheets.map((w) => {
                    const busy = busyWorksheetId === w.id;
                    return (
                    <tr key={w.id}>
                      <td>
                        {w.title}
                        {!w.is_published && (
                          <span className="badge badge-default" style={{ marginLeft: 8 }}>
                            Draft
                          </span>
                        )}
                      </td>
                      <td style={{ whiteSpace: 'nowrap' }}>
                        <a
                          href="/"
                          className="admin-action"
                          onClick={(e) => {
                            e.preventDefault();
                            navigate(`/assignments/${w.id}/edit`);
                          }}
                        >
                          Edit
                        </a>
                        <a
                          href="/"
                          className="admin-action"
                          onClick={(e) => {
                            e.preventDefault();
                            navigate(`/assignments/${w.id}/dashboard`);
                          }}
                        >
                          Live dashboard
                        </a>
                        <a
                          href="/"
                          className="admin-action"
                          onClick={(e) => {
                            e.preventDefault();
                            navigate(`/assignments/${w.id}/grades`);
                          }}
                        >
                          Grades
                        </a>
                        <a
                          href="/"
                          className="admin-action"
                          onClick={(e) => {
                            e.preventDefault();
                            if (!busy) handleTogglePublish(w);
                          }}
                        >
                          {busy ? '…' : w.is_published ? 'Unpublish' : 'Publish'}
                        </a>
                        <a
                          href="/"
                          className="admin-action admin-action-danger"
                          onClick={(e) => {
                            e.preventDefault();
                            if (!busy) handleDelete(w);
                          }}
                        >
                          {busy ? 'Deleting…' : 'Delete'}
                        </a>
                      </td>
                    </tr>
                    );
                  })}
                  {worksheets.length === 0 && (
                    <tr>
                      <td colSpan={2} style={{ color: 'var(--muted)', textAlign: 'center', padding: 20 }}>
                        No assignments yet — create one below.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div style={{ marginTop: 12 }}>
              {!showNewForm && (
                <button className="btn btn-sm" onClick={() => setShowNewFormFor(c.id)}>
                  + Create New
                </button>
              )}
              {showNewForm && (
                <div className="panel" style={{ maxWidth: 460 }}>
                  <div className="panel-body">
                    <form onSubmit={(e) => handleCreateAssignment(e, c.id)}>
                      <div className="form-group">
                        <label htmlFor={`newTitle-${c.id}`}>Title</label>
                        <input
                          id={`newTitle-${c.id}`}
                          className="form-control"
                          value={newTitle}
                          onChange={(e) => setNewTitle(e.target.value)}
                          required
                          autoFocus
                        />
                      </div>
                      <div className="form-group">
                        <label htmlFor={`newDescription-${c.id}`}>Description (optional)</label>
                        <input
                          id={`newDescription-${c.id}`}
                          className="form-control"
                          value={newDescription}
                          onChange={(e) => setNewDescription(e.target.value)}
                        />
                      </div>
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button className="btn btn-primary" type="submit" disabled={creating}>
                          {creating ? 'Creating…' : 'Create assignment'}
                        </button>
                        <button className="btn" type="button" onClick={() => setShowNewFormFor(null)}>
                          Cancel
                        </button>
                      </div>
                    </form>
                  </div>
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
