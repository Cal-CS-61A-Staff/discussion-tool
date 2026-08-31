import { useEffect, useState } from 'react';
import * as sectionsApi from '../../api/sections.js';

/** The course roster (ClassEnrollment) — shown to any TA/co-teacher on the
 * class (and admins) on ClassSectionsPage. A rostered student may join a
 * group under any section of the class; a class with an empty roster stays
 * open to anyone. */
export default function ClassStudentsPanel({ classId }) {
  const [students, setStudents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);

  const load = () => {
    setLoading(true);
    sectionsApi
      .listClassStudents(classId)
      .then((data) => setStudents(data.students))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classId]);

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    setError('');
    setBusy(true);
    try {
      await sectionsApi.addClassStudent(classId, email.trim(), name.trim() || undefined);
      setEmail('');
      setName('');
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async (student) => {
    if (!window.confirm(`Remove ${student.name || student.email} from the roster?`)) return;
    setError('');
    setBusy(true);
    try {
      await sectionsApi.removeClassStudent(classId, student.email);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel-heading">
        <h4>Students ({students.length})</h4>
        <span style={{ fontSize: 11, color: 'var(--muted)' }}>the course roster — who can join a group</span>
      </div>
      <div className="panel-body">
        {error && <div className="alert alert-danger">{error}</div>}

        <form onSubmit={handleAdd} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
          <input
            className="form-control"
            style={{ maxWidth: 260 }}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="student's email"
            disabled={busy}
          />
          <input
            className="form-control"
            style={{ maxWidth: 200 }}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="name (optional)"
            disabled={busy}
          />
          <button type="submit" className="btn btn-sm" disabled={busy || !email.trim()}>
            {busy ? 'Adding…' : '+ Add student'}
          </button>
        </form>

        {loading ? (
          <p style={{ color: 'var(--muted)' }}>Loading…</p>
        ) : students.length === 0 ? (
          <p style={{ fontSize: 13, color: 'var(--muted)', margin: 0 }}>
            No roster yet — anyone can join a group in this class until you add someone.
          </p>
        ) : (
          <div className="table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {students.map((s) => (
                  <tr key={s.email}>
                    <td>{s.name || <span style={{ color: 'var(--muted)' }}>—</span>}</td>
                    <td>{s.email}</td>
                    <td style={{ color: 'var(--muted)', fontSize: 13 }}>
                      {s.in_group ? 'in a group' : s.has_account ? 'signed in, no group' : 'not signed in yet'}
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <a
                        href="/"
                        className="admin-action admin-action-danger"
                        onClick={(e) => {
                          e.preventDefault();
                          if (!busy) handleRemove(s);
                        }}
                      >
                        Remove
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
