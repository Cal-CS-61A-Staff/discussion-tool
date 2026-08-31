import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import CourseCard from '../components/home/CourseCard.jsx';
import * as adminApi from '../api/admin.js';
import * as sectionsApi from '../api/sections.js';
import { useAuth } from '../context/AuthContext.jsx';
import { isAdmin, isStaff } from '../utils/roles.js';

export default function HomePage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [classes, setClasses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [showNewForm, setShowNewForm] = useState(false);
  const [newCourseName, setNewCourseName] = useState('');
  const [creating, setCreating] = useState(false);

  const load = () => {
    sectionsApi
      .listClasses()
      .then((res) => setClasses(res.classes))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const handleCreateCourse = async (e) => {
    e.preventDefault();
    setCreating(true);
    setError('');
    try {
      await adminApi.createClass(newCourseName.trim());
      setNewCourseName('');
      setShowNewForm(false);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  };

  const viewCourse = (course) => navigate(`/assignments?classId=${course.id}`);

  if (loading) return <div className="page-loading">Loading…</div>;

  const activeClasses = classes.filter((c) => !c.is_archived);
  const pastClasses = classes.filter((c) => c.is_archived);

  return (
    <div>
      <div className="jumbotron">
        <div>
          <h1>CS 61A Discussion</h1>
          <p>
            Welcome, {user.display_name}.{' '}
            {isStaff(user) ? 'Pick a class below to manage its assignments and groups.' : 'Pick your class below to see its assignments.'}
          </p>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="page-header-row">
        <h1>Active Courses</h1>
      </div>
      <div className="card-holder">
        {isAdmin(user) &&
          (showNewForm ? (
            <div className="panel">
              <div className="panel-body">
                <form onSubmit={handleCreateCourse}>
                  <div className="form-group">
                    <label htmlFor="newCourseName">Course name</label>
                    <input
                      id="newCourseName"
                      className="form-control"
                      value={newCourseName}
                      onChange={(e) => setNewCourseName(e.target.value)}
                      placeholder="e.g. CS 61A"
                      required
                      autoFocus
                    />
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn btn-primary btn-sm" type="submit" disabled={creating}>
                      {creating ? 'Creating…' : 'Create course'}
                    </button>
                    <button className="btn btn-sm" type="button" onClick={() => setShowNewForm(false)}>
                      Cancel
                    </button>
                  </div>
                </form>
              </div>
            </div>
          ) : (
            <button type="button" className="course-card-create" onClick={() => setShowNewForm(true)}>
              <span className="course-card-create-plus">+</span>
              Create a New Course
            </button>
          ))}
        {activeClasses.map((c) => (
          <CourseCard key={c.id} course={c} onClick={() => viewCourse(c)} />
        ))}
        {activeClasses.length === 0 && !isAdmin(user) && (
          <p style={{ color: 'var(--muted)' }}>No active classes yet.</p>
        )}
      </div>

      {pastClasses.length > 0 && (
        <>
          <div className="page-header-row" style={{ marginTop: 32 }}>
            <h1>Past Courses</h1>
          </div>
          <div className="card-holder">
            {pastClasses.map((c) => (
              <CourseCard key={c.id} course={c} onClick={() => viewCourse(c)} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
