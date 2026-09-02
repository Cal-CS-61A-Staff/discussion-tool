import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import CourseCard from '../components/home/CourseCard.jsx';
import * as adminApi from '../api/admin.js';
import * as sectionsApi from '../api/sections.js';
import { useAuth } from '../context/AuthContext.jsx';
import { isAdmin } from '../utils/roles.js';

export default function HomePage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [classes, setClasses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [showNewForm, setShowNewForm] = useState(false);
  const [newCourseName, setNewCourseName] = useState('');
  const [creating, setCreating] = useState(false);

  const [joinCode, setJoinCode] = useState('');
  const [joining, setJoining] = useState(false);
  const [joinError, setJoinError] = useState('');

  const load = () => {
    sectionsApi
      .listClasses()
      .then((res) => setClasses(res.classes))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  const handleJoinClass = async (e) => {
    e.preventDefault();
    setJoining(true);
    setJoinError('');
    try {
      await sectionsApi.joinClass(joinCode.trim());
      setJoinCode('');
      load();
    } catch (err) {
      setJoinError(err.message);
    } finally {
      setJoining(false);
    }
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
            Welcome, {user.display_name}. Pick a class below, or enter a join code to add one.
          </p>
          <form onSubmit={handleJoinClass} style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
            <input
              className="form-control"
              style={{ maxWidth: 200 }}
              value={joinCode}
              onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
              placeholder="Class join code"
              disabled={joining}
            />
            <button className="btn btn-sm" type="submit" disabled={joining || !joinCode.trim()}>
              {joining ? 'Joining…' : 'Join a class'}
            </button>
          </form>
          {joinError && <p style={{ color: 'var(--danger, #d9534f)', fontSize: 13, margin: '6px 0 0' }}>{joinError}</p>}
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
