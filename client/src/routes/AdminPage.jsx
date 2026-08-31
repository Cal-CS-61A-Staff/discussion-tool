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

  const [rosterText, setRosterText] = useState('');
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState('');
  const [importSummary, setImportSummary] = useState(null);

  const [enrollmentText, setEnrollmentText] = useState('');
  const [enrollmentImporting, setEnrollmentImporting] = useState(false);
  const [enrollmentError, setEnrollmentError] = useState('');
  const [enrollmentSummary, setEnrollmentSummary] = useState(null);

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
    setImporting(true);
    setImportError('');
    setImportSummary(null);
    try {
      const res = await adminApi.importRoster(rosterText);
      setImportSummary(res.summary);
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

  const handleImportEnrollment = async (e) => {
    e.preventDefault();
    setEnrollmentImporting(true);
    setEnrollmentError('');
    setEnrollmentSummary(null);
    try {
      const res = await adminApi.importEnrollmentRoster(enrollmentText);
      setEnrollmentSummary(res.summary);
      load();
    } catch (err) {
      setEnrollmentError(err.message);
    } finally {
      setEnrollmentImporting(false);
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

      {tas.length === 0 && (
        <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 12 }}>
          No TA accounts yet — a TA needs to sign in once (Student/TA login, "TA / Instructor") before you can assign
          them to a class.
        </p>
      )}

      <div className="panel" style={{ marginTop: 24 }}>
        <div className="panel-heading">
          <h4>Import TA roster</h4>
        </div>
        <div className="panel-body">
          <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 0 }}>
            Paste the staff-assignment sheet — TA name, then repeating Section/Groups column pairs — straight from
            Google Sheets (tab-separated). Each TA is matched by name (creating a new TA account if none matches),
            and each Section column becomes a class assigned to that TA. The "Groups" columns are read but not used —
            those group-number ranges are on a different, global numbering scheme this app doesn't use; add groups to
            an imported class from its "Manage groups" page afterward.
          </p>
          <form onSubmit={handleImportRoster}>
            <div className="form-group">
              <textarea
                className="form-control code"
                rows={8}
                value={rosterText}
                onChange={(e) => setRosterText(e.target.value)}
                placeholder={'TA\tSection 1\tGroups\tSection 2\tGroups\n...'}
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
            <button className="btn btn-primary" type="submit" disabled={importing || !rosterText.trim()}>
              {importing ? 'Importing…' : 'Import roster'}
            </button>
          </form>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 24 }}>
        <div className="panel-heading">
          <h4>Import student enrollment</h4>
        </div>
        <div className="panel-body">
          <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 0 }}>
            Paste the per-student enrollment export — columns{' '}
            <code className="code">Student Email, Staff Email, Location, Day, Start, Type</code> — straight from
            Google Sheets (tab-separated). Only rows where Type is "Discussion" are used; Lab/Office Hours/Lecture
            rows are skipped. Each unique (Day, Start, Location) becomes a class assigned to that row's Staff Email,
            and every Student Email is recorded as enrolled in it — which discussion section a student belongs to,
            not which group. A student can join any group within their enrolled section; trying to join a group in a
            different section they're not enrolled in is rejected.
          </p>
          <form onSubmit={handleImportEnrollment}>
            <div className="form-group">
              <textarea
                className="form-control code"
                rows={8}
                value={enrollmentText}
                onChange={(e) => setEnrollmentText(e.target.value)}
                placeholder={'Student Email\tStaff Email\tLocation\tDay\tStart\tType\n...'}
                required
              />
            </div>
            {enrollmentError && <div className="alert alert-danger">{enrollmentError}</div>}
            {enrollmentSummary && (
              <div className="alert alert-success">
                Sections: {enrollmentSummary.sections_created} created, {enrollmentSummary.sections_matched} matched.
                TAs: {enrollmentSummary.tas_created} created, {enrollmentSummary.tas_matched} matched. Enrollments:{' '}
                {enrollmentSummary.enrollments_created} created, {enrollmentSummary.enrollments_matched} matched.
              </div>
            )}
            <button className="btn btn-primary" type="submit" disabled={enrollmentImporting || !enrollmentText.trim()}>
              {enrollmentImporting ? 'Importing…' : 'Import enrollment'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
