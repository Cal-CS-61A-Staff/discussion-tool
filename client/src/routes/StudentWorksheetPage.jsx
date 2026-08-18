import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import CodeEditor from '../components/student/CodeEditor.jsx';
import ConfidenceScale from '../components/student/ConfidenceScale.jsx';
import GroupMembersStrip from '../components/student/GroupMembersStrip.jsx';
import MarkdownContent from '../components/student/MarkdownContent.jsx';
import NextQuestionButton from '../components/student/NextQuestionButton.jsx';
import ProgressStrip from '../components/student/ProgressStrip.jsx';
import ScratchEditor from '../components/student/ScratchEditor.jsx';
import TestRunner from '../components/student/TestRunner.jsx';
import TypistBanner from '../components/student/TypistBanner.jsx';
import { useAuth } from '../context/AuthContext.jsx';
import * as groupsApi from '../api/groups.js';
import { usePolling } from '../hooks/usePolling.js';

export default function StudentWorksheetPage() {
  const { sectionId, worksheetId, groupId } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [localCode, setLocalCode] = useState('');
  const [actionError, setActionError] = useState('');
  const codeDirtyRef = useRef(false);
  const debounceRef = useRef(null);
  const lastQuestionIdRef = useRef(null);

  const fetchState = useCallback(
    (signal) => groupsApi.getGroupState(groupId, worksheetId, signal),
    [groupId, worksheetId]
  );
  const { data, error, loading, refetch } = usePolling(fetchState, { intervalMs: 2500 });

  // Reset local edit state on question change, and pull in the server's
  // code buffer whenever we're not the one mid-edit (avoids clobbering the
  // typist's own in-progress keystrokes on every poll).
  useEffect(() => {
    if (!data || data.group.completed) return;
    const changedQuestion = lastQuestionIdRef.current !== data.question.id;
    if (changedQuestion) {
      lastQuestionIdRef.current = data.question.id;
      codeDirtyRef.current = false;
    }
    if (!codeDirtyRef.current) {
      setLocalCode(data.code);
    }
  }, [data]);

  if (loading && !data) return <div className="page-loading">Loading…</div>;
  if (error && !data) {
    return (
      <div className="page-loading">
        Couldn&apos;t load this group: {error.message}
        {error.status === 403 && <div>You may not be a member of this group.</div>}
      </div>
    );
  }
  if (!data) return null;

  const backToAssignment = () => navigate(`/classes/${sectionId}/assignments/${worksheetId}`);

  const breadcrumb = (
    <div className="breadcrumb-row">
      <a
        href="/"
        onClick={(e) => {
          e.preventDefault();
          backToAssignment();
        }}
      >
        ← Back to assignment
      </a>
      <span>·</span>
      <span>{data.group.name}</span>
    </div>
  );

  if (data.group.completed) {
    return (
      <div>
        {breadcrumb}
        <div className="panel">
          <div className="panel-body">
            <h2>Assignment complete</h2>
            <p>Your group has finished all {data.total_questions} questions. Nice work!</p>
          </div>
        </div>
      </div>
    );
  }

  const me = data.members.find((m) => m.is_me);
  const isMeTypist = Boolean(me?.is_typist);
  const ratedCount = data.members.filter((m) => m.has_rated_current).length;
  const currentTypist = data.members.find((m) => m.is_typist);

  const clearError = () => setActionError('');

  const handleClaim = async () => {
    clearError();
    try {
      await groupsApi.claimTypist(groupId, worksheetId);
      await refetch();
    } catch (err) {
      setActionError(err.message);
    }
  };

  const handlePass = async (toUserId) => {
    clearError();
    try {
      await groupsApi.passTypist(groupId, worksheetId, toUserId);
      await refetch();
    } catch (err) {
      setActionError(err.message);
    }
  };

  const handleCodeChange = (value) => {
    setLocalCode(value);
    codeDirtyRef.current = true;
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      groupsApi.updateCode(groupId, worksheetId, value).catch((err) => setActionError(err.message));
    }, 500);
  };

  const handleRate = async (value) => {
    clearError();
    try {
      await groupsApi.submitRating(groupId, worksheetId, value);
      await refetch();
    } catch (err) {
      setActionError(err.message);
    }
  };

  const handleAdvance = async () => {
    clearError();
    try {
      await groupsApi.advanceGroup(groupId, worksheetId);
      codeDirtyRef.current = false;
      await refetch();
    } catch (err) {
      setActionError(err.message);
    }
  };

  const handleGoBack = async () => {
    clearError();
    try {
      await groupsApi.goBack(groupId, worksheetId);
      codeDirtyRef.current = false;
      await refetch();
    } catch (err) {
      setActionError(err.message);
    }
  };

  return (
    <div>
      {breadcrumb}
      <div className="page-header-row" style={{ marginTop: 0 }}>
        <h1>{data.group.name}</h1>
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>{data.members.length} in group</span>
      </div>

      <ProgressStrip current={data.group.current_question_index} total={data.total_questions} />
      {data.group.current_question_index > 0 && (
        <button className="btn btn-sm" style={{ marginBottom: 14 }} onClick={handleGoBack}>
          ← Previous question
        </button>
      )}
      <TypistBanner members={data.members} isMeTypist={isMeTypist} onPass={handlePass} onClaim={handleClaim} />

      <div className="panel worksheet-panel">
        <div className="panel-body">
          {actionError && <div className="alert alert-danger">{actionError}</div>}

          <div className="q-label">
            Question {data.question.order_index + 1} — {data.question.title}
          </div>
          <MarkdownContent content={data.question.prompt} />

          <CodeEditor
            code={localCode}
            readOnly={!isMeTypist}
            onChange={handleCodeChange}
            editorLabel={isMeTypist ? "You're editing" : `${currentTypist?.display_name || 'Someone'} is editing`}
          />

          <TestRunner
            key={data.question.id}
            groupId={groupId}
            worksheetId={worksheetId}
            source="shared"
            code={localCode}
            predictCall={data.question.predict_call}
            disabled={!isMeTypist}
            label="Run tests"
            graderCooldown={data.grader_cooldown}
            lastSharedRun={data.last_shared_run}
          />
        </div>
      </div>

      <ScratchEditor
        key={data.question.id}
        groupId={groupId}
        worksheetId={worksheetId}
        questionId={data.question.id}
        userId={user.id}
        predictCall={data.question.predict_call}
        starterCode={data.question.starter_code}
        graderCooldown={data.grader_cooldown}
      />

      <div className="panel">
        <div className="panel-heading">
          <h4>How are you feeling about this question?</h4>
          <span style={{ fontSize: 11, color: 'var(--muted)' }}>seen by your TA</span>
        </div>
        <div className="panel-body">
          <ConfidenceScale value={data.my_rating_value} onRate={handleRate} />
          <GroupMembersStrip members={data.members} />
          <NextQuestionButton
            ready={data.ready_to_advance}
            allRated={data.all_rated}
            hasPassingRun={data.has_passing_run}
            ratedCount={ratedCount}
            memberCount={data.members.length}
            onAdvance={handleAdvance}
          />
        </div>
      </div>
    </div>
  );
}
