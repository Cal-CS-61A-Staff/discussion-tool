import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import ClassFilterSelect from '../components/shared/ClassFilterSelect.jsx';
import * as adminApi from '../api/admin.js';
import * as sectionsApi from '../api/sections.js';
import { useAuth } from '../context/AuthContext.jsx';
import { classIsStaff } from '../utils/roles.js';

export default function AssignmentsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const filterClassId = searchParams.get('classId');

  const handleClassFilterChange = (classId) => {
    setSearchParams(classId ? { classId: String(classId) } : {});
  };

  const [classes, setClasses] = useState([]);
  const [worksheetsByClass, setWorksheetsByClass] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [showNewFormFor, setShowNewFormFor] = useState(null);
  const [newTitle, setNewTitle] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [creating, setCreating] = useState(false);
  const [busyWorksheetId, setBusyWorksheetId] = useState(null);
  const [viewingAsStudentId, setViewingAsStudentId] = useState(null);

  const load = () => {
    setLoading(true);
    let fetched = [];
    sectionsApi
      .listClasses()
      .then((res) => {
        fetched = res.classes;
        setClasses(res.classes);
        return Promise.all(fetched.map((c) => sectionsApi.classWorksheets(c.id)));
      })
      .then((results) => {
        const byClass = {};
        results.forEach((res, i) => {
          byClass[fetched[i].id] = res.worksheets;
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
    const confirmMessage = w.is_published
      ? `Unpublish "${w.title}"? Students will no longer be able to see or access it.`
      : `Publish "${w.title}"? Students will immediately be able to see and start it.`;
    if (!window.confirm(confirmMessage)) return;
    setBusyWorksheetId(w.id);
    setError('');
    try {
      if (w.is_published) await adminApi.unpublishWorksheet(w.id);
      else await adminApi.publishWorksheet(w.id);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyWorksheetId(null);
    }
  };

  // Drops a staff member into the same share-link flow a student gets, to
  // sanity-check an assignment before publishing it. Staff keep a stable
  // "staff-" participant key (server/participant.py), and their solo group
  // is excluded from grade rollups.
  const handleViewAsStudent = (worksheet) => {
    if (worksheet.share_code) navigate(`/w/${worksheet.share_code}`);
    else setError('Publish this assignment first to preview it as a student.');
  };

  // Assignments belong to a class. This lands on AssignmentPage first (where
  // the student enters a group number) — never straight into a live group.
  const goToAssignment = (classId, worksheetId) => {
    navigate(`/classes/${classId}/assignments/${worksheetId}`);
  };

  if (loading) return <div className="page-loading">Loading…</div>;

  const visibleClasses = filterClassId ? classes.filter((c) => String(c.id) === filterClassId) : classes;

  return (
    <div>
      <div className="page-header-row">
        <div>
          <h1>Assignments</h1>
          <p>Shared across a whole class — any staff member of that class can edit them.</p>
        </div>
        {classes.length > 1 && (
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label htmlFor="classFilter" style={{ fontSize: 12 }}>
              Class
            </label>
            <ClassFilterSelect
              id="classFilter"
              classes={classes}
              value={filterClassId ? Number(filterClassId) : null}
              onChange={handleClassFilterChange}
            />
          </div>
        )}
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {visibleClasses.length === 0 && (
        <p style={{ color: 'var(--muted)' }}>
          Nothing here yet — enter a class join code on the home page.
        </p>
      )}

      {visibleClasses.map((c) => {
        const worksheets = worksheetsByClass[c.id] || [];
        const staff = classIsStaff(c, user);
        const showNewForm = showNewFormFor === c.id;
        return (
          <div key={c.id} style={{ marginBottom: 32 }}>
            <h3 style={{ marginBottom: 10 }}>{c.course_name}</h3>

            {staff ? (
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
                      const viewingAsStudent = viewingAsStudentId === w.id;
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
                                if (!viewingAsStudent) handleViewAsStudent(w);
                              }}
                            >
                              {viewingAsStudent ? 'Starting…' : 'View as student'}
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
            ) : (
              <p style={{ color: 'var(--muted)', fontSize: 13 }}>
                Students open the share link their TA hands out — there’s nothing to pick here.
              </p>
            )}

            {staff && (
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
            )}
          </div>
        );
      })}
    </div>
  );
}
