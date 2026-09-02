import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ClassFilterSelect from '../components/shared/ClassFilterSelect.jsx';
import * as adminApi from '../api/admin.js';
import * as sectionsApi from '../api/sections.js';
import { useAuth } from '../context/AuthContext.jsx';
import { isStaff } from '../utils/roles.js';

const staffClasses = (classes, user) =>
  classes.filter((c) => user?.role === 'admin' || c.my_role === 'staff');

export default function DiscussionsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isAdmin = user.role === 'admin';

  const [classes, setClasses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filterClassId, setFilterClassId] = useState(null);

  const [showNewForm, setShowNewForm] = useState(false);
  const [newClassName, setNewClassName] = useState('');
  const [creating, setCreating] = useState(false);

  const load = () => {
    setLoading(true);
    sectionsApi
      .listClasses()
      .then((res) => setClasses(staffClasses(res.classes, user)))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const handleCreateClass = async (e) => {
    e.preventDefault();
    setCreating(true);
    setError('');
    try {
      const res = await adminApi.createClass(newClassName.trim());
      setNewClassName('');
      setShowNewForm(false);
      navigate(`/discussions/${res.klass.id}`);
    } catch (err) {
      setError(err.message);
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
      <div className="page-header-row">
        <div>
          <h1>Discussions</h1>
          <p>{isAdmin ? 'Every class — click one to manage its rooms and staff.' : 'Classes you teach or co-teach in.'}</p>
        </div>
        {classes.length > 1 && (
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label htmlFor="classFilter" style={{ fontSize: 12 }}>
              Class
            </label>
            <ClassFilterSelect id="classFilter" classes={classes} value={filterClassId} onChange={setFilterClassId} />
          </div>
        )}
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Class</th>
              <th>Rooms</th>
            </tr>
          </thead>
          <tbody>
            {classes.filter((c) => !filterClassId || c.id === filterClassId).map((c) => (
              <tr key={c.id}>
                <td>
                  <a
                    href="/"
                    onClick={(e) => {
                      e.preventDefault();
                      navigate(`/discussions/${c.id}`);
                    }}
                  >
                    {c.course_name}
                  </a>
                </td>
                <td>{c.section_count}</td>
              </tr>
            ))}
            {classes.length === 0 && (
              <tr>
                <td colSpan={2} style={{ color: 'var(--muted)', textAlign: 'center', padding: 20 }}>
                  {isAdmin ? 'No classes yet — create one below.' : "You don't teach or co-teach in any classes yet."}
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
              + New class
            </button>
          )}
          {showNewForm && (
            <div className="panel" style={{ maxWidth: 380 }}>
              <div className="panel-body">
                <form onSubmit={handleCreateClass}>
                  <div className="form-group">
                    <label htmlFor="newClassName">Course name</label>
                    <input
                      id="newClassName"
                      className="form-control"
                      value={newClassName}
                      onChange={(e) => setNewClassName(e.target.value)}
                      placeholder="e.g. CS 61A"
                      required
                      autoFocus
                    />
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn btn-primary" type="submit" disabled={creating}>
                      {creating ? 'Creating…' : 'Create class'}
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
