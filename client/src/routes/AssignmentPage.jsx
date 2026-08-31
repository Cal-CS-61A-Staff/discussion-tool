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
  const [classSections, setClassSections] = useState([]);
  const [myGroupInClass, setMyGroupInClass] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [joining, setJoining] = useState(false);
  const [workingIndividually, setWorkingIndividually] = useState(false);
  const [showSwitchGroup, setShowSwitchGroup] = useState(false);

  // Which section's groups the student is browsing on the join panel —
  // starts at the section in the URL but they can switch TA freely.
  const [joinSectionId, setJoinSectionId] = useState(sectionId);
  const [joinable, setJoinable] = useState([]);
  const [joinableLoading, setJoinableLoading] = useState(false);
  const [joinGroupNumber, setJoinGroupNumber] = useState('');

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
        const cid = section ? section.class_id : null;
        setClassId(cid);
        const inClass = sectionsRes.sections.filter((s) => s.class_id === cid);
        setClassSections(inClass);
        if (user.role === 'student') {
          const classSectionIds = new Set(inClass.map((s) => s.id));
          const mine = secondRes.groups.find((g) => !g.is_individual && classSectionIds.has(g.section_id));
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

  // Load the joinable-group list whenever the student is picking a group
  // and the chosen section changes.
  useEffect(() => {
    if (user.role !== 'student' || !joinSectionId) return;
    if (myGroupInClass && !showSwitchGroup) return;
    let cancelled = false;
    setJoinableLoading(true);
    setJoinGroupNumber('');
    sectionsApi
      .joinableGroups(joinSectionId)
      .then((res) => !cancelled && setJoinable(res.groups))
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setJoinableLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [joinSectionId, myGroupInClass, showSwitchGroup, user.role]);

  const goToWorksheet = (groupSectionId, groupId) => {
    navigate(`/classes/${groupSectionId}/assignments/${worksheetId}/groups/${groupId}`);
  };

  const handleJoin = async (e) => {
    e.preventDefault();
    if (!joinGroupNumber) return;
    setJoining(true);
    setError('');
    try {
      const res = await sectionsApi.joinGroupByNumber(joinSectionId, Number(joinGroupNumber));
      goToWorksheet(joinSectionId, res.group.id);
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
      const res = await sectionsApi.workIndividually(joinSectionId || sectionId);
      goToWorksheet(joinSectionId || sectionId, res.group.id);
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
                onClick={() => goToWorksheet(myGroupInClass.section_id, myGroupInClass.id)}
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
                  Switch group →
                </a>
              </p>
            </>
          ) : (
            <form onSubmit={handleJoin} className="panel" style={{ maxWidth: 420 }}>
              <div className="panel-body">
                <div className="form-group" style={{ marginBottom: 12 }}>
                  <label htmlFor="joinSection">Your TA / section</label>
                  <select
                    id="joinSection"
                    className="form-control"
                    value={joinSectionId}
                    onChange={(e) => setJoinSectionId(e.target.value)}
                  >
                    {[...classSections]
                      .sort((a, b) => (a.ta_name || '~').localeCompare(b.ta_name || '~'))
                      .map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.ta_name ? `${s.ta_name} — ${s.name}` : s.name}
                        </option>
                      ))}
                  </select>
                </div>
                <div className="form-group" style={{ marginBottom: 12 }}>
                  <label htmlFor="joinGroup">Group</label>
                  <select
                    id="joinGroup"
                    className="form-control"
                    value={joinGroupNumber}
                    disabled={joinableLoading || joinable.length === 0}
                    onChange={(e) => setJoinGroupNumber(e.target.value)}
                  >
                    <option value="" disabled>
                      {joinableLoading ? 'Loading…' : joinable.length === 0 ? 'No groups yet' : 'Choose a group…'}
                    </option>
                    {joinable.map((g) => (
                      <option key={g.id} value={g.number} disabled={g.is_full}>
                        {g.name} — {g.member_count}/{g.capacity}
                        {g.is_full ? ' (full)' : ''}
                      </option>
                    ))}
                  </select>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn btn-primary" type="submit" disabled={joining || !joinGroupNumber}>
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

          {(!myGroupInClass || showSwitchGroup) && (
            <>
              <p style={{ margin: '16px 0 8px', fontSize: 13, color: 'var(--muted)' }}>or</p>
              <button className="btn btn-gold" onClick={handleWorkIndividually} disabled={workingIndividually}>
                {workingIndividually ? 'Setting up…' : 'Work individually'}
              </button>
            </>
          )}
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
