import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import TaQuestionList from '../components/ta/TaQuestionList.jsx';
import * as adminApi from '../api/admin.js';
import * as sectionsApi from '../api/sections.js';
import { useAuth } from '../context/AuthContext.jsx';

export default function AssignmentPage() {
  const { classId, worksheetId } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [worksheet, setWorksheet] = useState(null);
  const [staff, setStaff] = useState(false);
  const [questions, setQuestions] = useState([]);
  const [myGroup, setMyGroup] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [groupNumber, setGroupNumber] = useState('');
  const [groupName, setGroupName] = useState('');
  const [joining, setJoining] = useState(false);
  const [workingIndividually, setWorkingIndividually] = useState(false);
  const [switching, setSwitching] = useState(false);

  const load = () => {
    setLoading(true);
    Promise.all([sectionsApi.listClasses(), sectionsApi.classWorksheets(classId), sectionsApi.myGroups()])
      .then(([classesRes, worksheetsRes, groupsRes]) => {
        const klass = classesRes.classes.find((c) => String(c.id) === String(classId));
        const isStaff = user.role === 'admin' || klass?.my_role === 'staff';
        setStaff(isStaff);
        const found = worksheetsRes.worksheets.find((w) => String(w.id) === String(worksheetId));
        setWorksheet(found || null);
        setMyGroup(
          groupsRes.groups.find((g) => !g.is_individual && String(g.class_id) === String(classId)) || null
        );
        if (isStaff) {
          return adminApi.listQuestions(worksheetId).then((res) => setQuestions(res.questions));
        }
        return undefined;
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classId, worksheetId]);

  const goToWorksheet = (groupId) => navigate(`/classes/${classId}/assignments/${worksheetId}/groups/${groupId}`);

  const handleJoin = async (e) => {
    e.preventDefault();
    if (!groupNumber) return;
    setJoining(true);
    setError('');
    try {
      const res = await sectionsApi.joinGroupByNumber(classId, Number(groupNumber), groupName.trim() || undefined);
      goToWorksheet(res.group.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setJoining(false);
    }
  };

  const handleWorkIndividually = async () => {
    setWorkingIndividually(true);
    setError('');
    try {
      const res = await sectionsApi.workIndividually(classId);
      goToWorksheet(res.group.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setWorkingIndividually(false);
    }
  };

  if (loading) return <div className="page-loading">Loading…</div>;

  return (
    <div>
      <div className="breadcrumb-row">
        <a
          href="/"
          onClick={(e) => {
            e.preventDefault();
            navigate(`/assignments?classId=${classId}`);
          }}
        >
          ← Back to assignments
        </a>
      </div>
      <div className="page-header-row">
        <div>
          <h1>{worksheet ? worksheet.title : 'Assignment'}</h1>
          {worksheet?.description && <p>{worksheet.description}</p>}
        </div>
        {staff && (
          <div style={{ display: 'flex', gap: 14 }}>
            <a
              href="/"
              onClick={(e) => {
                e.preventDefault();
                navigate(`/assignments/${worksheetId}/dashboard`);
              }}
            >
              Live dashboard →
            </a>
            <a
              href="/"
              onClick={(e) => {
                e.preventDefault();
                navigate(`/assignments/${worksheetId}/edit`);
              }}
            >
              Edit assignment →
            </a>
          </div>
        )}
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {!staff && (
        <>
          {myGroup && !switching ? (
            <>
              <div
                className="panel panel-clickable"
                style={{ maxWidth: 360 }}
                onClick={() => goToWorksheet(myGroup.id)}
              >
                <div className="panel-heading">
                  <h4>{myGroup.name}</h4>
                  <span className="badge badge-success">yours</span>
                </div>
                <div className="panel-body">
                  <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)' }}>
                    Group {myGroup.number} · click to resume
                  </p>
                </div>
              </div>
              <p style={{ margin: '10px 0 0' }}>
                <a
                  href="/"
                  style={{ fontSize: 13 }}
                  onClick={(e) => {
                    e.preventDefault();
                    setSwitching(true);
                  }}
                >
                  Enter a different number →
                </a>
              </p>
            </>
          ) : (
            <form onSubmit={handleJoin} className="panel" style={{ maxWidth: 420 }}>
              <div className="panel-body">
                <div className="form-group" style={{ marginBottom: 12 }}>
                  <label htmlFor="groupNumber">Group number</label>
                  <input
                    id="groupNumber"
                    type="number"
                    min="1"
                    className="form-control"
                    value={groupNumber}
                    onChange={(e) => setGroupNumber(e.target.value)}
                    placeholder="e.g. 7"
                    autoFocus
                  />
                  <p style={{ fontSize: 12, color: 'var(--muted)', margin: '4px 0 0' }}>
                    Everyone who enters the same number works together.
                  </p>
                </div>
                <div className="form-group" style={{ marginBottom: 12 }}>
                  <label htmlFor="groupName">Group name (optional)</label>
                  <input
                    id="groupName"
                    className="form-control"
                    value={groupName}
                    onChange={(e) => setGroupName(e.target.value)}
                    placeholder="shown at the top for your group"
                  />
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn btn-primary" type="submit" disabled={joining || !groupNumber}>
                    {joining ? 'Joining…' : 'Join group'}
                  </button>
                  {myGroup && (
                    <button className="btn" type="button" onClick={() => setSwitching(false)}>
                      Cancel
                    </button>
                  )}
                </div>
              </div>
            </form>
          )}

          {(!myGroup || switching) && (
            <>
              <p style={{ margin: '16px 0 8px', fontSize: 13, color: 'var(--muted)' }}>or</p>
              <button className="btn btn-gold" onClick={handleWorkIndividually} disabled={workingIndividually}>
                {workingIndividually ? 'Setting up…' : 'Work individually'}
              </button>
            </>
          )}
        </>
      )}

      {staff && (
        <>
          <div className="page-header-row" style={{ marginTop: 0 }}>
            <h3 style={{ margin: 0 }}>Questions ({questions.length})</h3>
          </div>
          <TaQuestionList questions={questions} />
        </>
      )}
    </div>
  );
}
