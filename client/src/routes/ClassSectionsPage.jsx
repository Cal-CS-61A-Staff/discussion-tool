import { Fragment, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import SectionGroupsPanel from '../components/ta/SectionGroupsPanel.jsx';
import * as adminApi from '../api/admin.js';
import * as sectionsApi from '../api/sections.js';
import { useAuth } from '../context/AuthContext.jsx';
import { isStaff } from '../utils/roles.js';

export default function ClassSectionsPage() {
  const { classId } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const isAdmin = user.role === 'admin';

  const [className, setClassName] = useState('');
  const [sections, setSections] = useState([]);
  const [tas, setTas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [editingId, setEditingId] = useState(null);
  const [editName, setEditName] = useState('');
  const [expandedId, setExpandedId] = useState(null);
  const [groupsExpandedId, setGroupsExpandedId] = useState(null);
  const [coTeacherInput, setCoTeacherInput] = useState('');
  const [busySectionId, setBusySectionId] = useState(null);

  const [showNewForm, setShowNewForm] = useState(false);
  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);

  const load = () => {
    setLoading(true);
    const calls = isAdmin
      ? [sectionsApi.listClasses(), sectionsApi.listSections(), adminApi.listTas()]
      : [sectionsApi.listClasses(), sectionsApi.listSections()];
    Promise.all(calls)
      .then(([classesRes, sectionsRes, tasRes]) => {
        const klass = classesRes.classes.find((c) => String(c.id) === String(classId));
        setClassName(klass ? klass.course_name : 'Class');
        setSections(sectionsRes.sections.filter((s) => String(s.class_id) === String(classId)));
        if (tasRes) setTas(tasRes.tas);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classId]);

  const startEdit = (section) => {
    setEditingId(section.id);
    setEditName(section.name);
  };

  const saveEdit = async (sectionId) => {
    setBusySectionId(sectionId);
    setError('');
    try {
      await sectionsApi.updateSectionDetails(sectionId, editName.trim());
      setEditingId(null);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusySectionId(null);
    }
  };

  const handleAssignTa = async (section, taUserId) => {
    setBusySectionId(section.id);
    setError('');
    try {
      await adminApi.assignSectionTa(section.id, taUserId || null);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusySectionId(null);
    }
  };

  const toggleExpanded = (section) => {
    setExpandedId(expandedId === section.id ? null : section.id);
    setCoTeacherInput('');
  };

  const toggleGroupsExpanded = (section) => {
    setGroupsExpandedId(groupsExpandedId === section.id ? null : section.id);
  };

  const handleAddCoTeacher = async (section) => {
    const email = coTeacherInput.trim();
    if (!email) return;
    setBusySectionId(section.id);
    setError('');
    try {
      await sectionsApi.addCoTeacher(section.id, email);
      setCoTeacherInput('');
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusySectionId(null);
    }
  };

  const handleRemoveCoTeacher = async (section, coTeacher) => {
    if (!window.confirm(`Remove ${coTeacher.display_name} as a co-teacher of "${section.name}"?`)) {
      return;
    }
    setBusySectionId(section.id);
    setError('');
    try {
      await sectionsApi.removeCoTeacher(section.id, coTeacher.id);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusySectionId(null);
    }
  };

  const handleDeleteSection = async (section) => {
    if (
      !window.confirm(`Delete "${section.name}"? This permanently removes every group and history in this section.`)
    ) {
      return;
    }
    setBusySectionId(section.id);
    setError('');
    try {
      await sectionsApi.deleteSection(section.id);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusySectionId(null);
    }
  };

  const handleCreateSection = async (e) => {
    e.preventDefault();
    setCreating(true);
    setError('');
    try {
      await sectionsApi.createSection(Number(classId), newName.trim());
      setNewName('');
      setShowNewForm(false);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
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
      <div className="breadcrumb-row">
        <a
          href="/"
          onClick={(e) => {
            e.preventDefault();
            navigate('/discussions');
          }}
        >
          ← All classes
        </a>
      </div>
      <div className="page-header-row">
        <div>
          <h1>{className}</h1>
          <p>Sections {isAdmin ? 'in this class' : 'you teach or co-teach in this class'}.</p>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Section</th>
              <th>TA</th>
              <th>Co-teachers</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {sections.map((section) => {
              const editing = editingId === section.id;
              const expanded = expandedId === section.id;
              const busy = busySectionId === section.id;
              return (
                <Fragment key={section.id}>
                  <tr>
                    <td>
                      {editing ? (
                        <input
                          className="form-control"
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          autoFocus
                        />
                      ) : (
                        section.name
                      )}
                    </td>
                    <td>
                      {isAdmin ? (
                        <select
                          className="form-control"
                          style={{ maxWidth: 220 }}
                          value={section.ta_id || ''}
                          disabled={busy}
                          onChange={(e) => handleAssignTa(section, e.target.value ? Number(e.target.value) : null)}
                        >
                          <option value="">Unassigned</option>
                          {tas.map((t) => (
                            <option key={t.id} value={t.id}>
                              {t.display_name}
                              {t.role === 'admin' ? ' (admin)' : ''}
                              {t.email ? ` — ${t.email}` : ''}
                            </option>
                          ))}
                        </select>
                      ) : section.ta_name ? (
                        <span>
                          {section.ta_name}
                          {section.ta_email && (
                            <span style={{ color: 'var(--muted)', fontSize: 12 }}> ({section.ta_email})</span>
                          )}
                        </span>
                      ) : (
                        <span style={{ color: 'var(--muted)' }}>Unassigned</span>
                      )}
                    </td>
                    <td>
                      {section.co_teachers.length > 0 ? (
                        section.co_teachers.map((c) => c.display_name).join(', ')
                      ) : (
                        <span style={{ color: 'var(--muted)' }}>none</span>
                      )}
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      {editing ? (
                        <>
                          <a
                            href="/"
                            className="admin-action"
                            onClick={(e) => {
                              e.preventDefault();
                              if (!busy) saveEdit(section.id);
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
                            startEdit(section);
                          }}
                        >
                          Rename
                        </a>
                      )}
                      <a
                        href="/"
                        className="admin-action"
                        onClick={(e) => {
                          e.preventDefault();
                          toggleExpanded(section);
                        }}
                      >
                        Co-teachers
                      </a>
                      <a
                        href="/"
                        className="admin-action"
                        onClick={(e) => {
                          e.preventDefault();
                          toggleGroupsExpanded(section);
                        }}
                      >
                        Manage groups
                      </a>
                      {isAdmin && (
                        <a
                          href="/"
                          className="admin-action admin-action-danger"
                          onClick={(e) => {
                            e.preventDefault();
                            if (!busy) handleDeleteSection(section);
                          }}
                        >
                          {busy ? 'Deleting…' : 'Delete'}
                        </a>
                      )}
                    </td>
                  </tr>
                  {expanded && (
                    <tr>
                      <td colSpan={4} style={{ background: 'var(--bg-subtle, #f7f8f9)' }}>
                        <p style={{ fontSize: 12, color: 'var(--muted)', margin: '4px 0 8px' }}>
                          A co-teacher gets the exact same access to this section as its TA.
                        </p>
                        {section.co_teachers.length > 0 && (
                          <div className="list-group" style={{ marginBottom: 10, maxWidth: 420 }}>
                            {section.co_teachers.map((c) => (
                              <div
                                key={c.id}
                                className="list-group-item"
                                style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                              >
                                <span>
                                  {c.display_name}
                                  {c.email && <span style={{ color: 'var(--muted)' }}> ({c.email})</span>}
                                </span>
                                <a
                                  href="/"
                                  className="admin-action admin-action-danger"
                                  onClick={(e) => {
                                    e.preventDefault();
                                    if (!busy) handleRemoveCoTeacher(section, c);
                                  }}
                                >
                                  {busy ? 'Removing…' : 'Remove'}
                                </a>
                              </div>
                            ))}
                          </div>
                        )}
                        <div style={{ display: 'flex', gap: 8 }}>
                          <input
                            className="form-control"
                            style={{ maxWidth: 280 }}
                            type="email"
                            value={coTeacherInput}
                            onChange={(e) => setCoTeacherInput(e.target.value)}
                            placeholder="co-teacher's email"
                            disabled={busy}
                          />
                          <button
                            type="button"
                            className="btn btn-sm"
                            disabled={busy || !coTeacherInput.trim()}
                            onClick={() => handleAddCoTeacher(section)}
                          >
                            {busy ? 'Adding…' : '+ Add co-teacher'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}
                  {groupsExpandedId === section.id && (
                    <tr>
                      <td colSpan={4} style={{ background: 'var(--bg-subtle, #f7f8f9)' }}>
                        <SectionGroupsPanel sectionId={section.id} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
            {sections.length === 0 && (
              <tr>
                <td colSpan={4} style={{ color: 'var(--muted)', textAlign: 'center', padding: 20 }}>
                  {isAdmin ? 'No sections yet — create one below.' : "You don't teach or co-teach any of this class's sections."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {isAdmin && (
        <div style={{ marginTop: 20 }}>
          {!showNewForm && (
            <button className="btn btn-primary" onClick={() => setShowNewForm(true)}>
              + New section
            </button>
          )}
          {showNewForm && (
            <div className="panel" style={{ maxWidth: 380 }}>
              <div className="panel-body">
                <form onSubmit={handleCreateSection}>
                  <div className="form-group">
                    <label htmlFor="newSectionName">Section name</label>
                    <input
                      id="newSectionName"
                      className="form-control"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      placeholder='e.g. "Disc 12" or "R 2:00 PM-3:29 PM (VLSB2070)"'
                      required
                      autoFocus
                    />
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn btn-primary" type="submit" disabled={creating}>
                      {creating ? 'Creating…' : 'Create section'}
                    </button>
                    <button className="btn" type="button" onClick={() => setShowNewForm(false)}>
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
}
