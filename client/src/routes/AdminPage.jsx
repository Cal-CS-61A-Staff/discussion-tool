import { useEffect, useState } from 'react';
import ClassFilterSelect from '../components/shared/ClassFilterSelect.jsx';
import * as adminApi from '../api/admin.js';
import * as sectionsApi from '../api/sections.js';
import { useAuth } from '../context/AuthContext.jsx';

export default function AdminPage() {
  const { user } = useAuth();
  const [sections, setSections] = useState([]);
  const [classes, setClasses] = useState([]);
  const [tas, setTas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [savingId, setSavingId] = useState(null);
  const [archivingId, setArchivingId] = useState(null);

  const [filterClassId, setFilterClassId] = useState(null);

  const [rosterFile, setRosterFile] = useState(null);
  const [rosterFileInputKey, setRosterFileInputKey] = useState(0);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState('');
  const [importSummary, setImportSummary] = useState(null);

  const [studentFile, setStudentFile] = useState(null);
  const [studentFileInputKey, setStudentFileInputKey] = useState(0);
  const [studentClassId, setStudentClassId] = useState('');
  const [studentImporting, setStudentImporting] = useState(false);
  const [studentError, setStudentError] = useState('');
  const [studentSummary, setStudentSummary] = useState(null);

  const [newTaEmail, setNewTaEmail] = useState('');
  const [newTaName, setNewTaName] = useState('');
  const [addingTa, setAddingTa] = useState(false);
  const [addTaError, setAddTaError] = useState('');

  const [newAdminEmail, setNewAdminEmail] = useState('');
  const [newAdminName, setNewAdminName] = useState('');
  const [addingAdmin, setAddingAdmin] = useState(false);
  const [addAdminError, setAddAdminError] = useState('');

  const readFileText = (file) =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error || new Error('Could not read file'));
      reader.readAsText(file);
    });

  const load = () => {
    setLoading(true);
    Promise.all([sectionsApi.listSections(), sectionsApi.listClasses(), adminApi.listTas()])
      .then(([sectionsRes, classesRes, tasRes]) => {
        setSections(sectionsRes.sections);
        setClasses(classesRes.classes);
        setTas(tasRes.tas);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const handleAssign = async (section, taUserId) => {
    setSavingId(section.id);
    setError('');
    try {
      await adminApi.assignSectionTa(section.id, taUserId || null);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingId(null);
    }
  };

  const handleImportRoster = async (e) => {
    e.preventDefault();
    if (!rosterFile) return;
    setImporting(true);
    setImportError('');
    setImportSummary(null);
    try {
      const text = await readFileText(rosterFile);
      const res = await adminApi.importRoster(text);
      setImportSummary(res.summary);
      setRosterFile(null);
      setRosterFileInputKey((k) => k + 1);
      load();
    } catch (err) {
      setImportError(err.message);
    } finally {
      setImporting(false);
    }
  };

  const handleToggleArchive = async (klass) => {
    setArchivingId(klass.id);
    setError('');
    try {
      await adminApi.archiveClass(klass.id, !klass.is_archived);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setArchivingId(null);
    }
  };

  const handleImportStudents = async (e) => {
    e.preventDefault();
    if (!studentFile || !studentClassId) return;
    setStudentImporting(true);
    setStudentError('');
    setStudentSummary(null);
    try {
      const text = await readFileText(studentFile);
      const res = await adminApi.importStudentRoster(text, Number(studentClassId));
      setStudentSummary(res.summary);
      setStudentFile(null);
      setStudentFileInputKey((k) => k + 1);
      load();
    } catch (err) {
      setStudentError(err.message);
    } finally {
      setStudentImporting(false);
    }
  };

  const handleAddTa = async (e) => {
    e.preventDefault();
    if (!newTaEmail.trim()) return;
    setAddingTa(true);
    setAddTaError('');
    try {
      await adminApi.addTa(newTaEmail.trim(), newTaName.trim() || undefined);
      setNewTaEmail('');
      setNewTaName('');
      load();
    } catch (err) {
      setAddTaError(err.message);
    } finally {
      setAddingTa(false);
    }
  };

  const handleAddAdmin = async (e) => {
    e.preventDefault();
    if (!newAdminEmail.trim()) return;
    setAddingAdmin(true);
    setAddAdminError('');
    try {
      await adminApi.addAdmin(newAdminEmail.trim(), newAdminName.trim() || undefined);
      setNewAdminEmail('');
      setNewAdminName('');
      load();
    } catch (err) {
      setAddAdminError(err.message);
    } finally {
      setAddingAdmin(false);
    }
  };

  if (user.role !== 'admin') {
    return (
      <div className="panel">
        <div className="panel-body">Admin access required.</div>
      </div>
    );
  }

  if (loading) return <div className="page-loading">Loading…</div>;

  const visibleSections = filterClassId ? sections.filter((s) => s.class_id === filterClassId) : sections;
  // listTas() already returns 'ta' and 'admin' users together, tagged with role.
  const admins = tas.filter((t) => t.role === 'admin');

  return (
    <div>
      <div className="page-header-row">
        <div>
          <h1>Admin</h1>
          <p>Assign the TA who owns each class — a TA only sees and manages their own class's groups.</p>
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

      <div className="panel">
        <div className="panel-heading">
          <h4>Classes</h4>
        </div>
        <div className="table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Class</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {classes.map((klass) => (
                <tr key={klass.id}>
                  <td>{klass.course_name}</td>
                  <td>
                    <span className={`badge ${klass.is_archived ? 'badge-default' : 'badge-success'}`}>
                      {klass.is_archived ? 'Archived' : 'Active'}
                    </span>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-sm"
                      onClick={() => handleToggleArchive(klass)}
                      disabled={archivingId === klass.id}
                    >
                      {archivingId === klass.id ? '…' : klass.is_archived ? 'Restore' : 'Archive'}
                    </button>
                  </td>
                </tr>
              ))}
              {classes.length === 0 && (
                <tr>
                  <td colSpan={3} style={{ color: 'var(--muted)', textAlign: 'center', padding: 20 }}>
                    No classes yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <h3>Section TAs</h3>
      <div className="table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Class</th>
              <th>Assigned TA</th>
            </tr>
          </thead>
          <tbody>
            {visibleSections.map((s) => (
              <tr key={s.id}>
                <td>
                  {s.course_name} · {s.name}
                </td>
                <td>
                  <select
                    className="form-control"
                    style={{ maxWidth: 260 }}
                    value={s.ta_id || ''}
                    disabled={savingId === s.id}
                    onChange={(e) => handleAssign(s, e.target.value ? Number(e.target.value) : null)}
                  >
                    <option value="">Unassigned</option>
                    {tas.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.display_name}
                        {t.email ? ` — ${t.email}` : ''}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
            {visibleSections.length === 0 && (
              <tr>
                <td colSpan={2} style={{ color: 'var(--muted)', textAlign: 'center', padding: 20 }}>
                  No classes yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <form onSubmit={handleAddTa} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
        <input
          className="form-control"
          style={{ maxWidth: 240 }}
          type="email"
          value={newTaEmail}
          onChange={(e) => setNewTaEmail(e.target.value)}
          placeholder="new TA's email"
          disabled={addingTa}
        />
        <input
          className="form-control"
          style={{ maxWidth: 200 }}
          value={newTaName}
          onChange={(e) => setNewTaName(e.target.value)}
          placeholder="name (optional)"
          disabled={addingTa}
        />
        <button className="btn btn-sm" type="submit" disabled={addingTa || !newTaEmail.trim()}>
          {addingTa ? 'Adding…' : '+ Add a TA'}
        </button>
      </form>
      {addTaError && <div className="alert alert-danger" style={{ marginTop: 8 }}>{addTaError}</div>}
      <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 8 }}>
        A TA added by email can be assigned to a section right away, before they've ever signed in.
      </p>

      <div className="panel" style={{ marginTop: 24 }}>
        <div className="panel-heading">
          <h4>Admins</h4>
        </div>
        <div className="panel-body">
          <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 0 }}>
            Granting admin is additive — it layers every admin-only power (assigning section TAs,
            creating and archiving classes, roster imports) on top of whatever the person can already
            do, so a TA promoted here keeps all their sections. Matched by email; a brand-new account
            can be granted admin before they've ever signed in.
          </p>
          {admins.length > 0 && (
            <ul style={{ margin: '0 0 12px', paddingLeft: 18, fontSize: 13 }}>
              {admins.map((a) => (
                <li key={a.id}>
                  {a.display_name}
                  {a.email ? ` — ${a.email}` : ''}
                  {a.id === user.id && ' (you)'}
                </li>
              ))}
            </ul>
          )}
          <form onSubmit={handleAddAdmin} style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <input
              className="form-control"
              style={{ maxWidth: 240 }}
              type="email"
              value={newAdminEmail}
              onChange={(e) => setNewAdminEmail(e.target.value)}
              placeholder="new admin's email"
              disabled={addingAdmin}
            />
            <input
              className="form-control"
              style={{ maxWidth: 200 }}
              value={newAdminName}
              onChange={(e) => setNewAdminName(e.target.value)}
              placeholder="name (optional)"
              disabled={addingAdmin}
            />
            <button className="btn btn-sm" type="submit" disabled={addingAdmin || !newAdminEmail.trim()}>
              {addingAdmin ? 'Adding…' : '+ Add an admin'}
            </button>
          </form>
          {addAdminError && <div className="alert alert-danger" style={{ marginTop: 8 }}>{addAdminError}</div>}
        </div>
      </div>

      <div className="panel" style={{ marginTop: 24 }}>
        <div className="panel-heading">
          <h4>Import TA roster</h4>
        </div>
        <div className="panel-body">
          <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 0 }}>
            Upload a CSV with columns <code className="code">Name, Email, Sections</code> — where <em>Sections</em> is
            one cell holding a <code className="code">;</code>-separated list of the section labels that TA teaches.
            In Google Sheets: File → Download → Comma Separated Values (.csv). Each TA is matched by email (created if
            new), and each listed section is created under CS 61A and assigned to them.
          </p>
          <form onSubmit={handleImportRoster}>
            <div className="form-group">
              <input
                key={rosterFileInputKey}
                type="file"
                accept=".csv,text/csv"
                onChange={(e) => setRosterFile(e.target.files[0] || null)}
                required
              />
            </div>
            {importError && <div className="alert alert-danger">{importError}</div>}
            {importSummary && (
              <div className="alert alert-success">
                TAs: {importSummary.tas_created} created, {importSummary.tas_matched} matched. Sections:{' '}
                {importSummary.sections_created} created, {importSummary.sections_assigned} assignments made.
              </div>
            )}
            <button className="btn btn-primary" type="submit" disabled={importing || !rosterFile} style={{ marginTop: 12 }}>
              {importing ? 'Importing…' : 'Import roster'}
            </button>
          </form>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 24 }}>
        <div className="panel-heading">
          <h4>Import student roster</h4>
        </div>
        <div className="panel-body">
          <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 0 }}>
            Pick a class, then upload a CSV with columns <code className="code">Email, Name</code> (Name optional).
            Every email is added to that class's roster; a rostered student can join a group under any section of
            the class. A class with an empty roster stays open to anyone.
          </p>
          <form onSubmit={handleImportStudents}>
            <div className="form-group">
              <select
                className="form-control"
                style={{ maxWidth: 280 }}
                value={studentClassId}
                onChange={(e) => setStudentClassId(e.target.value)}
                required
              >
                <option value="" disabled>
                  Choose a class…
                </option>
                {classes.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.course_name}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <input
                key={studentFileInputKey}
                type="file"
                accept=".csv,text/csv"
                onChange={(e) => setStudentFile(e.target.files[0] || null)}
                required
              />
            </div>
            {studentError && <div className="alert alert-danger">{studentError}</div>}
            {studentSummary && (
              <div className="alert alert-success">
                Enrollments: {studentSummary.enrollments_created} created, {studentSummary.enrollments_matched}{' '}
                matched. {studentSummary.students_created} placeholder student accounts created.
              </div>
            )}
            <button
              className="btn btn-primary"
              type="submit"
              disabled={studentImporting || !studentFile || !studentClassId}
              style={{ marginTop: 12 }}
            >
              {studentImporting ? 'Importing…' : 'Import students'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
