import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import TaQuestionList from '../components/ta/TaQuestionList.jsx';
import * as adminApi from '../api/admin.js';
import * as sectionsApi from '../api/sections.js';
import { useAuth } from '../context/AuthContext.jsx';
import { isStaff } from '../utils/roles.js';

export default function AssignmentPage() {
  const { sectionId, worksheetId } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [worksheet, setWorksheet] = useState(null);
  const [classId, setClassId] = useState(null);
  const [myGroupInClass, setMyGroupInClass] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [groupNumber, setGroupNumber] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [joining, setJoining] = useState(false);
  const [workingIndividually, setWorkingIndividually] = useState(false);
  const [showSwitchGroup, setShowSwitchGroup] = useState(false);

  const load = () => {
    setLoading(true);
    const calls =
      user.role === 'student'
        ? [sectionsApi.sectionWorksheets(sectionId), sectionsApi.myGroups(), sectionsApi.listSections()]
        : [sectionsApi.sectionWorksheets(sectionId), adminApi.listQuestions(worksheetId), sectionsApi.listSections()];

    Promise.all(calls)
      .then(([worksheetsRes, secondRes, sectionsRes]) => {
        const found = worksheetsRes.worksheets.find((w) => String(w.id) === String(worksheetId));
        setWorksheet(found || null);
        const section = sectionsRes.sections.find((s) => String(s.id) === String(sectionId));
        setClassId(section ? section.class_id : null);
        if (user.role === 'student') {
          const mine = secondRes.groups.find(
            (g) => String(g.section_id) === String(sectionId) && !g.is_individual
          );
          setMyGroupInClass(mine || null);
        } else {
          setQuestions(secondRes.questions);
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sectionId, worksheetId]);

  const goToWorksheet = (groupId) => {
    navigate(`/classes/${sectionId}/assignments/${worksheetId}/groups/${groupId}`);
  };

  const handleJoinByNumber = async (e) => {
    e.preventDefault();
    setJoining(true);
    setError('');
    try {
      const res = await sectionsApi.joinGroupByNumber(sectionId, Number(groupNumber));
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
      const res = await sectionsApi.workIndividually(sectionId);
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
            navigate(classId ? `/assignments?classId=${classId}` : '/assignments');
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
        {isStaff(user) && (
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

      {user.role === 'student' && (
        <>
          {myGroupInClass && !showSwitchGroup ? (
            <>
              <div
                className="panel panel-clickable"
                style={{ maxWidth: 360 }}
                onClick={() => goToWorksheet(myGroupInClass.id)}
              >
                <div className="panel-heading">
                  <h4>{myGroupInClass.name}</h4>
                  <span className="badge badge-success">yours</span>
                </div>
                <div className="panel-body">
                  <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)' }}>Click to resume</p>
                </div>
              </div>
              <p style={{ margin: '10px 0 0' }}>
                <a
                  href="/"
                  style={{ fontSize: 13 }}
                  onClick={(e) => {
                    e.preventDefault();
                    setShowSwitchGroup(true);
                  }}
                >
                  Enter a different group →
                </a>
              </p>
            </>
          ) : (
            <form onSubmit={handleJoinByNumber} className="panel" style={{ maxWidth: 360 }}>
              <div className="panel-body">
                <div className="form-group" style={{ marginBottom: 12 }}>
                  <label htmlFor="groupNumber">Group number</label>
                  <input
                    id="groupNumber"
                    className="form-control"
                    type="number"
                    min="1"
                    value={groupNumber}
                    onChange={(e) => setGroupNumber(e.target.value)}
                    placeholder="e.g. 3"
                    required
                    autoFocus
                  />
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn btn-primary" type="submit" disabled={joining}>
                    {joining ? 'Joining…' : 'Join group'}
                  </button>
                  {myGroupInClass && (
                    <button className="btn" type="button" onClick={() => setShowSwitchGroup(false)}>
                      Cancel
                    </button>
                  )}
                </div>
              </div>
            </form>
          )}

          <p style={{ margin: '16px 0 8px', fontSize: 13, color: 'var(--muted)' }}>or</p>
          <button className="btn btn-gold" onClick={handleWorkIndividually} disabled={workingIndividually}>
            {workingIndividually ? 'Setting up…' : 'Work individually'}
          </button>
        </>
      )}

      {isStaff(user) && (
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
