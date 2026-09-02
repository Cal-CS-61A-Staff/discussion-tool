import { useEffect, useState } from 'react';
import * as adminApi from '../api/admin.js';
import * as sectionsApi from '../api/sections.js';
import { useAuth } from '../context/AuthContext.jsx';

export default function AdminPage() {
  const { user } = useAuth();
  const [classes, setClasses] = useState([]);
  const [admins, setAdmins] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [archivingId, setArchivingId] = useState(null);

  const [rosterFile, setRosterFile] = useState(null);
  const [rosterFileInputKey, setRosterFileInputKey] = useState(0);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState('');
  const [importSummary, setImportSummary] = useState(null);

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
    Promise.all([sectionsApi.listClasses(), adminApi.listAdmins()])
      .then(([classesRes, adminsRes]) => {
        setClasses(classesRes.classes);
        setAdmins(adminsRes.admins);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

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

  return (
    <div>
      <div className="page-header-row">
        <div>
          <h1>Admin</h1>
          <p>Classes, global admins, and the staff-roster import. Per-class staff and rooms live on each class's Rooms page.</p>
        </div>
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
                <th>Join code</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {classes.map((klass) => (
                <tr key={klass.id}>
                  <td>{klass.course_name}</td>
                  <td>
                    <code className="code">{klass.join_code || '—'}</code>
                  </td>
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
                  <td colSpan={4} style={{ color: 'var(--muted)', textAlign: 'center', padding: 20 }}>
                    No classes yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 24 }}>
        <div className="panel-heading">
          <h4>Admins</h4>
        </div>
        <div className="panel-body">
          <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 0 }}>
            An admin is a global super-user — every class, plus creating/archiving classes and roster import. Matched
            by email; can be granted before the person has ever signed in.
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
          <h4>Import staff roster</h4>
        </div>
        <div className="panel-body">
          <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 0 }}>
            Upload a CSV with columns <code className="code">Name, Email, Sections</code> — where <em>Sections</em> is
            one cell holding a <code className="code">;</code>-separated list of room labels that person runs. Each is
            matched by email (created if new), granted class staff on CS 61A, and made the TA of each listed room.
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
                Staff: {importSummary.tas_created} created, {importSummary.tas_matched} matched. Rooms:{' '}
                {importSummary.sections_created} created, {importSummary.sections_assigned} assignments made.
              </div>
            )}
            <button className="btn btn-primary" type="submit" disabled={importing || !rosterFile} style={{ marginTop: 12 }}>
              {importing ? 'Importing…' : 'Import roster'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
