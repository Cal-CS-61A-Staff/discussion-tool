import { Fragment, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import * as adminApi from '../api/admin.js';
import * as sectionsApi from '../api/sections.js';
import { useAuth } from '../context/AuthContext.jsx';
import { classIsStaff } from '../utils/roles.js';

export default function ClassSectionsPage() {
  const { classId } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const isAdmin = user.role === 'admin';

  const [klass, setKlass] = useState(null);
  const [sections, setSections] = useState([]);
  const [staff, setStaff] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [editingId, setEditingId] = useState(null);
  const [editName, setEditName] = useState('');
  const [editNumbers, setEditNumbers] = useState('');
  const [expandedId, setExpandedId] = useState(null);
  const [coTeacherInput, setCoTeacherInput] = useState('');
  const [busySectionId, setBusySectionId] = useState(null);

  const [showNewForm, setShowNewForm] = useState(false);
  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);

  const [newStaffEmail, setNewStaffEmail] = useState('');
  const [addingStaff, setAddingStaff] = useState(false);

  const load = () => {
    setLoading(true);
    Promise.all([sectionsApi.listClasses(), sectionsApi.listSections(), sectionsApi.listClassStaff(classId)])
      .then(([classesRes, sectionsRes, staffRes]) => {
        setKlass(classesRes.classes.find((c) => String(c.id) === String(classId)) || null);
        setSections(sectionsRes.sections.filter((s) => String(s.class_id) === String(classId)));
        setStaff(staffRes.staff);
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
    setEditNumbers(section.assigned_numbers || '');
  };

  const saveEdit = async (sectionId) => {
    setBusySectionId(sectionId);
    setError('');
    try {
      await sectionsApi.updateSectionDetails(sectionId, editName.trim(), editNumbers.trim());
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
    if (!window.confirm(`Remove ${coTeacher.display_name} from "${section.name}"?`)) return;
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
    if (!window.confirm(`Delete room "${section.name}"? Groups and history are unaffected.`)) return;
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

  const handleAddStaff = async (e) => {
    e.preventDefault();
    if (!newStaffEmail.trim()) return;
    setAddingStaff(true);
    setError('');
    try {
      await sectionsApi.addClassStaff(classId, newStaffEmail.trim());
      setNewStaffEmail('');
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setAddingStaff(false);
    }
  };

  const handleRemoveStaff = async (member) => {
    if (!window.confirm(`Remove ${member.display_name} from this class's staff?`)) return;
    setError('');
    try {
      await sectionsApi.removeClassStaff(classId, member.user_id);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  if (loading) return <div className="page-loading">Loading…</div>;

  if (klass && !classIsStaff(klass, user)) {
    return (
      <div className="panel">
        <div className="panel-body">You're not staff of this class.</div>
      </div>
    );
  }

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
          <h1>{klass ? klass.course_name : 'Class'}</h1>
          {klass?.join_code && (
            <p>
              Join code: <code className="code">{klass.join_code}</code> — share this with students so they can add
              the class.
            </p>
          )}
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="panel">
        <div className="panel-heading">
          <h4>Class staff</h4>
        </div>
        <div className="panel-body">
          {staff.length > 0 && (
            <ul style={{ margin: '0 0 12px', paddingLeft: 18, fontSize: 13 }}>
              {staff.map((m) => (
                <li key={m.user_id} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span>
                    {m.display_name}
                    {m.email ? ` — ${m.email}` : ''}
                    {m.user_id === user.id && ' (you)'}
                  </span>
                  <a
                    href="/"
                    className="admin-action admin-action-danger"
                    onClick={(e) => {
                      e.preventDefault();
                      handleRemoveStaff(m);
                    }}
                  >
                    remove
                  </a>
                </li>
              ))}
            </ul>
          )}
          <form onSubmit={handleAddStaff} style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <input
              className="form-control"
              style={{ maxWidth: 260 }}
              type="email"
              value={newStaffEmail}
              onChange={(e) => setNewStaffEmail(e.target.value)}
              placeholder="new staff member's email"
              disabled={addingStaff}
            />
            <button className="btn btn-sm" type="submit" disabled={addingStaff || !newStaffEmail.trim()}>
              {addingStaff ? 'Adding…' : '+ Add staff'}
            </button>
          </form>
        </div>
      </div>

      <h3 style={{ marginTop: 24 }}>Rooms</h3>
      <p style={{ fontSize: 13, color: 'var(--muted)', marginTop: 0 }}>
        A room is just a name and the group numbers it covers — it seeds a TA's live-dashboard watch list. Students
        never see rooms.
      </p>
      <div className="table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Room</th>
              <th>Group numbers</th>
              <th>TA</th>
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
                      {editing ? (
                        <input
                          className="form-control"
                          style={{ maxWidth: 160 }}
                          value={editNumbers}
                          onChange={(e) => setEditNumbers(e.target.value)}
                          placeholder="e.g. 1-8,12"
                        />
                      ) : (
                        section.assigned_numbers || <span style={{ color: 'var(--muted)' }}>none</span>
                      )}
                    </td>
                    <td>
                      <select
                        className="form-control"
                        style={{ maxWidth: 220 }}
                        value={section.ta_id || ''}
                        disabled={busy}
                        onChange={(e) => handleAssignTa(section, e.target.value ? Number(e.target.value) : null)}
                      >
                        <option value="">Unassigned</option>
                        {staff.map((m) => (
                          <option key={m.user_id} value={m.user_id}>
                            {m.display_name}
                            {m.email ? ` — ${m.email}` : ''}
                          </option>
                        ))}
                      </select>
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
                          Edit
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
                          A co-teacher must already be class staff; they get this room's numbers in their watch-list
                          seed too.
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
                </Fragment>
              );
            })}
            {sections.length === 0 && (
              <tr>
                <td colSpan={4} style={{ color: 'var(--muted)', textAlign: 'center', padding: 20 }}>
                  {isAdmin ? 'No rooms yet — create one below.' : 'No rooms yet.'}
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
              + New room
            </button>
          )}
          {showNewForm && (
            <div className="panel" style={{ maxWidth: 380 }}>
              <div className="panel-body">
                <form onSubmit={handleCreateSection}>
                  <div className="form-group">
                    <label htmlFor="newSectionName">Room name</label>
                    <input
                      id="newSectionName"
                      className="form-control"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      placeholder='e.g. "R 2:00 PM (VLSB 2050)"'
                      required
                      autoFocus
                    />
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn btn-primary" type="submit" disabled={creating}>
                      {creating ? 'Creating…' : 'Create room'}
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
