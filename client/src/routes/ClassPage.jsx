import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import * as adminApi from '../api/admin.js';
import * as sectionsApi from '../api/sections.js';
import { useAuth } from '../context/AuthContext.jsx';

export default function ClassPage() {
  const { sectionId } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [sectionName, setSectionName] = useState('');
  const [worksheets, setWorksheets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [showNewForm, setShowNewForm] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newDueDate, setNewDueDate] = useState('');
  const [creating, setCreating] = useState(false);

  const load = () => {
    setLoading(true);
    Promise.all([sectionsApi.listSections(), sectionsApi.sectionWorksheets(sectionId)])
      .then(([sectionsRes, worksheetsRes]) => {
        const section = sectionsRes.sections.find((s) => String(s.id) === String(sectionId));
        setSectionName(section ? `${section.course_name} · ${section.name}` : 'Class');
        setWorksheets(worksheetsRes.worksheets);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sectionId]);

  const handleCreateAssignment = async (e) => {
    e.preventDefault();
    setCreating(true);
    setError('');
    try {
      const res = await adminApi.createWorksheet(sectionId, {
        title: newTitle.trim(),
        description: newDescription.trim(),
        due_date: newDueDate || null,
      });
      navigate(`/classes/${sectionId}/assignments/${res.worksheet.id}/edit`);
    } catch (err) {
      setError(err.message);
      setCreating(false);
    }
  };

  const handleDelete = async (w) => {
    if (!window.confirm(`Delete "${w.title}"? This removes all its questions and group progress.`)) return;
    setError('');
    try {
      await adminApi.deleteWorksheet(w.id);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleTogglePublish = async (w) => {
    const verb = w.is_published ? 'unpublish' : 'publish';
    const confirmMessage = w.is_published
      ? `Unpublish "${w.title}"? Students will no longer be able to see or access it.`
      : `Publish "${w.title}"? Students will immediately be able to see and start it.`;
    if (!window.confirm(confirmMessage)) return;
    setError('');
    try {
      if (verb === 'unpublish') await adminApi.unpublishWorksheet(w.id);
      else await adminApi.publishWorksheet(w.id);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const formatDueDate = (due_date) => {
    if (!due_date) return 'No due date';
    return new Date(`${due_date}T00:00:00`).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  if (loading) return <div className="page-loading">Loading…</div>;

  return (
    <div>
      <div className="breadcrumb-row">
        <a
          href="/"
          onClick={(e) => {
            e.preventDefault();
            navigate('/');
          }}
        >
          ← Home
        </a>
      </div>
      <div className="page-header-row">
        <div>
          <h1>{sectionName}</h1>
          <p>Assignments in this class.</p>
        </div>
        {user.role === 'ta' && (
          <a
            href="/"
            onClick={(e) => {
              e.preventDefault();
              navigate(`/classes/${sectionId}/groups`);
            }}
          >
            Manage groups →
          </a>
        )}
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Problem Set Name</th>
              <th>Due Date</th>
              {user.role === 'ta' && <th>Actions</th>}
            </tr>
          </thead>
          <tbody>
            {worksheets.map((w) => (
              <tr key={w.id}>
                <td>
                  <a
                    href="/"
                    onClick={(e) => {
                      e.preventDefault();
                      navigate(`/classes/${sectionId}/assignments/${w.id}`);
                    }}
                  >
                    {w.title}
                  </a>
                  {user.role === 'ta' && !w.is_published && (
                    <span className="badge badge-default" style={{ marginLeft: 8 }}>
                      Draft
                    </span>
                  )}
                </td>
                <td style={{ color: w.due_date ? 'var(--ink)' : 'var(--muted)' }}>{formatDueDate(w.due_date)}</td>
                {user.role === 'ta' && (
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <a
                      href="/"
                      className="admin-action"
                      onClick={(e) => {
                        e.preventDefault();
                        navigate(`/classes/${sectionId}/assignments/${w.id}/edit`);
                      }}
                    >
                      Edit
                    </a>
                    <a
                      href="/"
                      className="admin-action"
                      onClick={(e) => {
                        e.preventDefault();
                        navigate(`/classes/${sectionId}/assignments/${w.id}/dashboard`);
                      }}
                    >
                      View Groups
                    </a>
                    <a
                      href="/"
                      className="admin-action"
                      onClick={(e) => {
                        e.preventDefault();
                        navigate(`/classes/${sectionId}/assignments/${w.id}/grades`);
                      }}
                    >
                      Grades
                    </a>
                    <a
                      href="/"
                      className="admin-action"
                      onClick={(e) => {
                        e.preventDefault();
                        handleTogglePublish(w);
                      }}
                    >
                      {w.is_published ? 'Unpublish' : 'Publish'}
                    </a>
                    <a
                      href="/"
                      className="admin-action admin-action-danger"
                      onClick={(e) => {
                        e.preventDefault();
                        handleDelete(w);
                      }}
                    >
                      Delete
                    </a>
                  </td>
                )}
              </tr>
            ))}
            {worksheets.length === 0 && (
              <tr>
                <td colSpan={user.role === 'ta' ? 3 : 2} style={{ color: 'var(--muted)', textAlign: 'center', padding: 20 }}>
                  {user.role === 'ta' ? 'No problem sets yet — create one below.' : 'No assignments yet.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {user.role === 'ta' && (
        <div style={{ marginTop: 20 }}>
          {!showNewForm && (
            <button className="btn btn-primary" onClick={() => setShowNewForm(true)}>
              + Create New
            </button>
          )}
          {showNewForm && (
            <div className="panel" style={{ maxWidth: 460 }}>
              <div className="panel-body">
                <form onSubmit={handleCreateAssignment}>
                  <div className="form-group">
                    <label htmlFor="newTitle">Title</label>
                    <input
                      id="newTitle"
                      className="form-control"
                      value={newTitle}
                      onChange={(e) => setNewTitle(e.target.value)}
                      required
                      autoFocus
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="newDescription">Description (optional)</label>
                    <input
                      id="newDescription"
                      className="form-control"
                      value={newDescription}
                      onChange={(e) => setNewDescription(e.target.value)}
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="newDueDate">Due date (optional)</label>
                    <input
                      id="newDueDate"
                      type="date"
                      className="form-control"
                      style={{ maxWidth: 200 }}
                      value={newDueDate}
                      onChange={(e) => setNewDueDate(e.target.value)}
                    />
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn btn-primary" type="submit" disabled={creating}>
                      {creating ? 'Creating…' : 'Create assignment'}
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
