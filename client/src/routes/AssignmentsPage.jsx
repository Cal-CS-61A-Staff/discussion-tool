import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import ClassFilterSelect from '../components/shared/ClassFilterSelect.jsx';
import * as adminApi from '../api/admin.js';
import * as sectionsApi from '../api/sections.js';
import { useAuth } from '../context/AuthContext.jsx';
import { isStaff } from '../utils/roles.js';

export default function AssignmentsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const filterClassId = searchParams.get('classId');
  const staff = isStaff(user);

  const handleClassFilterChange = (classId) => {
    setSearchParams(classId ? { classId: String(classId) } : {});
  };

  const [classes, setClasses] = useState([]);
  const [sections, setSections] = useState([]);
  const [myGroups, setMyGroups] = useState([]);
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
    let fetchedClasses = [];
    Promise.all([sectionsApi.listClasses(), sectionsApi.listSections(), sectionsApi.myGroups()])
      .then(([classesRes, sectionsRes, myGroupsRes]) => {
        fetchedClasses = classesRes.classes;
        setClasses(classesRes.classes);
        setSections(sectionsRes.sections);
        setMyGroups(myGroupsRes.groups);
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

  const viewWork = (w) => navigate(`/groups/${w.my_group_id}/worksheets/${w.id}/work`);

  // Drops a TA/admin into the exact same live worksheet flow a student
  // gets — their own solo "individual" group (server/blueprints/sections.py:
  // work_individually) — to sanity-check an assignment (doctests,
  // prediction quiz, wording) end to end before publishing it. Which
  // section it's filed under doesn't matter content-wise (a worksheet is
  // shared across the whole class); listSections() already only returns
  // sections this staff member has access to, so the first one is always
  // safe to use.
  const handleViewAsStudent = async (classId, worksheetId) => {
    const classSections = sections.filter((s) => s.class_id === classId);
    if (classSections.length === 0) {
      setError('Add a section to this class before previewing an assignment.');
      return;
    }
    setViewingAsStudentId(worksheetId);
    setError('');
    try {
      const res = await sectionsApi.workIndividually(classSections[0].id);
      navigate(`/classes/${classSections[0].id}/assignments/${worksheetId}/groups/${res.group.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setViewingAsStudentId(null);
    }
  };

  const sectionIdToClassId = Object.fromEntries(sections.map((s) => [s.id, s.class_id]));

  // Assignments belong to a class, not a section. This always lands on
  // AssignmentPage first, never straight into the live worksheet: joining
  // a group is a deliberate action (leaving the page gives up your
  // pen/active slot — see StudentWorksheetPage), not something to silently
  // re-enter on a stray click. AssignmentPage now hosts the "pick your TA
  // then a group" join panel itself, so we only need *a* section in the
  // URL — the student's own if they have a group, else any section of the
  // class as the starting point for the picker.
  const goToAssignment = (classId, worksheetId) => {
    const myGroup = myGroups.find((g) => sectionIdToClassId[g.section_id] === classId);
    if (myGroup) {
      navigate(`/classes/${myGroup.section_id}/assignments/${worksheetId}`);
      return;
    }
    const classSections = sections.filter((s) => s.class_id === classId);
    if (classSections.length === 0) {
      setError('No sections in this class yet — ask your TA.');
      return;
    }
    navigate(`/classes/${classSections[0].id}/assignments/${worksheetId}`);
  };

  if (loading) return <div className="page-loading">Loading…</div>;

  const visibleClasses = filterClassId ? classes.filter((c) => String(c.id) === filterClassId) : classes;

  return (
    <div>
      <div className="page-header-row">
        <div>
          <h1>Assignments</h1>
          <p>
            {staff
              ? 'Shared across every section of a class — any TA on that class\'s staff can edit them.'
              : 'Every discussion in your classes, with your own rating once you\'ve started one.'}
          </p>
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
          {staff
            ? "You don't own or co-teach any sections yet — assignments live under a class once you do."
            : 'Nothing here yet.'}
        </p>
      )}

      {visibleClasses.map((c) => {
        const worksheets = worksheetsByClass[c.id] || [];
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
                                if (!viewingAsStudent) handleViewAsStudent(c.id, w.id);
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
              <>
                {worksheets.length === 0 && (
                  <p style={{ color: 'var(--muted)', fontSize: 13 }}>Nothing released yet.</p>
                )}
                {/* Not-started assignments first — those are the ones actually worth surfacing. */}
                {[...worksheets]
                  .sort((a, b) => Number(Boolean(b.my_group_id)) - Number(Boolean(a.my_group_id)))
                  .map((w) => {
                  return (
                    <div className="panel panel-clickable" key={w.id} onClick={() => goToAssignment(c.id, w.id)}>
                      <div
                        className="panel-heading"
                        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                      >
                        <h4 style={{ margin: 0 }}>{w.title}</h4>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                          <div style={{ textAlign: 'right' }}>
                            <div style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase' }}>
                              Your confidence
                            </div>
                            <div style={{ fontSize: 18, fontWeight: 600 }}>
                              {w.my_rating != null ? `${w.my_rating} / 5` : w.my_group_id ? 'Not rated' : 'Not started'}
                            </div>
                          </div>
                          {w.my_group_id && (
                            <button
                              type="button"
                              className="btn btn-sm"
                              onClick={(e) => {
                                e.stopPropagation();
                                viewWork(w);
                              }}
                            >
                              View work
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </>
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
