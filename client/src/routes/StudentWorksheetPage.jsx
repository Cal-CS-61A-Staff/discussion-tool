import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import CodeEditor from '../components/student/CodeEditor.jsx';
import ConfidenceScale from '../components/student/ConfidenceScale.jsx';
import GroupMembersStrip from '../components/student/GroupMembersStrip.jsx';
import MarkdownContent from '../components/student/MarkdownContent.jsx';
import NextQuestionButton from '../components/student/NextQuestionButton.jsx';
import PracticeQuestion from '../components/student/PracticeQuestion.jsx';
import ProgressStrip from '../components/student/ProgressStrip.jsx';
import ScratchEditor from '../components/student/ScratchEditor.jsx';
import TestRunner from '../components/student/TestRunner.jsx';
import TypistBanner from '../components/student/TypistBanner.jsx';
import * as groupsApi from '../api/groups.js';
import { usePolling } from '../hooks/usePolling.js';

export default function StudentWorksheetPage() {
  const { sectionId, worksheetId, groupId } = useParams();
  const navigate = useNavigate();

  const [localCode, setLocalCode] = useState('');
  const [actionError, setActionError] = useState('');
  const [ratingSubmitting, setRatingSubmitting] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  const [givingUp, setGivingUp] = useState(false);
  // 'idle' | 'saving' | 'saved' | 'error' — feedback for the debounced
  // shared-code autosave (handleCodeChange below), since it's collaborative
  // and a typist should know their keystrokes actually reached the server.
  const [codeSaveStatus, setCodeSaveStatus] = useState('idle');
  const codeDirtyRef = useRef(false);
  const debounceRef = useRef(null);
  const lastQuestionIdRef = useRef(null);

  // null = following the group's in-focus question; a number = browsing an
  // earlier, already-unlocked one on our own — the group's shared progress
  // never moves for this (server/services/advance.py no longer has a
  // "go back" at all; see PracticeQuestion below for how browsing works).
  const [viewedIndex, setViewedIndex] = useState(null);
  const [viewedQuestion, setViewedQuestion] = useState(null);
  const [viewedLoading, setViewedLoading] = useState(false);
  const [viewedError, setViewedError] = useState('');

  const fetchState = useCallback(
    (signal) => groupsApi.getGroupState(groupId, worksheetId, signal),
    [groupId, worksheetId]
  );
  const { data, error, loading, refetch } = usePolling(fetchState, { intervalMs: 2500 });

  // In-app navigation away from this group/worksheet (Back, another
  // assignment, etc.) drops the pen and active-member status immediately
  // instead of waiting out the normal ~45s stale-poll timeout. Doesn't fire
  // on a closed tab or refresh — no reliable way to guarantee that in a
  // browser — so the stale-poll fallback still has to exist regardless.
  useEffect(() => {
    return () => {
      groupsApi.leaveGroup(groupId, worksheetId).catch(() => {});
    };
  }, [groupId, worksheetId]);

  const focusIndex = data?.group.current_question_index;

  // Snap back to the group's new focus whenever it actually moves — a
  // normal advance or someone using the "skip" escape hatch. Otherwise a
  // member who was browsing an earlier question when the group advanced
  // would silently keep viewing a question the whole group has now moved
  // past, instead of following along like everyone else.
  useEffect(() => {
    setViewedIndex(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusIndex]);
  const effectiveIndex = viewedIndex === null ? focusIndex : viewedIndex;
  const isViewingFocus = effectiveIndex === focusIndex;

  // Reset local edit state on question change, and pull in the server's
  // code buffer whenever we're not the one mid-edit (avoids clobbering the
  // typist's own in-progress keystrokes on every poll).
  useEffect(() => {
    if (!data || data.group.completed) return;
    const changedQuestion = lastQuestionIdRef.current !== data.question.id;
    if (changedQuestion) {
      lastQuestionIdRef.current = data.question.id;
      codeDirtyRef.current = false;
      setCodeSaveStatus('idle');
    }
    if (!codeDirtyRef.current) {
      setLocalCode(data.code);
    }
  }, [data]);

  // Load the browsed-away-from-focus question's content on demand — a
  // single GET already scoped to only what's unlocked so far
  // (server/services/serializers.py:build_group_work), then pick out the
  // one at effectiveIndex.
  useEffect(() => {
    if (!data || isViewingFocus) {
      setViewedQuestion(null);
      return;
    }
    let cancelled = false;
    setViewedLoading(true);
    setViewedError('');
    groupsApi
      .getGroupWork(groupId, worksheetId)
      .then((work) => {
        if (cancelled) return;
        const match = work.questions.find((q) => q.order_index === effectiveIndex);
        setViewedQuestion(match || null);
      })
      .catch((err) => !cancelled && setViewedError(err.message))
      .finally(() => !cancelled && setViewedLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupId, worksheetId, effectiveIndex, isViewingFocus]);

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

  // For a real group, AssignmentPage's "yours — click to resume" card gets
  // you straight back in. But that page only ever recognizes a *group*
  // group as "mine" (server/blueprints/sections.py:my_groups filters out
  // individual ones on purpose — there's nothing to "resume" via a group
  // picker for a solo worksheet) — so for individual mode it would always
  // show the join-a-group chooser, which makes no sense to land on when
  // you were just working solo. Skip straight past it to the assignments
  // list instead.
  const backToAssignment = () =>
    data.group.is_individual
      ? navigate('/assignments')
      : navigate(`/classes/${sectionId}/assignments/${worksheetId}`);

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
      <span>{data.worksheet_title}</span>
      <span>·</span>
      <span>{data.group.name}</span>
    </div>
  );

  if (data.group.completed) {
    return (
      <div>
        {breadcrumb}
        <div className="panel" style={{ marginTop: 16, textAlign: 'center' }}>
          <div className="panel-body" style={{ padding: '40px 20px' }}>
            <div style={{ fontSize: 40, marginBottom: 8 }}>🎉</div>
            <h2 style={{ margin: '0 0 4px' }}>Assignment complete</h2>
            <p style={{ color: 'var(--muted)', marginBottom: 24 }}>
              Your group has finished all {data.total_questions} questions. Nice work!
            </p>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
              <button type="button" className="btn" onClick={backToAssignment}>
                ← Back to assignment
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => navigate(`/groups/${groupId}/worksheets/${worksheetId}/work`)}
              >
                Review your answers
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const me = data.members.find((m) => m.is_me);
  const isMeTypist = Boolean(me?.is_typist);
  const ratedCount = data.members.filter((m) => m.has_rated_current).length;
  const activeCount = data.members.filter((m) => m.is_active).length;
  const currentTypist = data.members.find((m) => m.is_typist);
  // Same collision as TypistBanner — don't show your own name back at you
  // for someone else's account without a hint that it's not actually you.
  const currentTypistLabel =
    currentTypist && me && currentTypist.display_name === me.display_name
      ? `${currentTypist.display_name} (different account)`
      : currentTypist?.display_name || 'Someone';
  const isDiscussion = data.question.grading_mode === 'discussion';

  const clearError = () => setActionError('');

  const handleGiveUp = async () => {
    clearError();
    setGivingUp(true);
    try {
      await groupsApi.giveUpTypist(groupId, worksheetId);
      await refetch();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setGivingUp(false);
    }
  };

  const handleCodeChange = (value) => {
    setLocalCode(value);
    codeDirtyRef.current = true;
    setCodeSaveStatus('saving');
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      groupsApi
        .updateCode(groupId, worksheetId, value)
        .then(() => setCodeSaveStatus('saved'))
        .catch((err) => {
          setCodeSaveStatus('error');
          setActionError(err.message);
        });
    }, 500);
  };

  const handleRate = async (value) => {
    clearError();
    setRatingSubmitting(true);
    try {
      await groupsApi.submitRating(groupId, worksheetId, value);
      await refetch();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setRatingSubmitting(false);
    }
  };

  const handleAdvance = async () => {
    clearError();
    setAdvancing(true);
    try {
      await groupsApi.advanceGroup(groupId, worksheetId);
      codeDirtyRef.current = false;
      await refetch();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setAdvancing(false);
    }
  };

  const handleForceAdvance = async () => {
    clearError();
    setAdvancing(true);
    try {
      await groupsApi.forceAdvanceGroup(groupId, worksheetId);
      codeDirtyRef.current = false;
      await refetch();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setAdvancing(false);
    }
  };

  return (
    <div>
      {breadcrumb}
      {error && (
        <div className="alert alert-danger">
          Lost the connection to your group ({error.message}) — still trying every few seconds. What you see below
          may be out of date until it reconnects.
        </div>
      )}
      <div className="page-header-row" style={{ marginTop: 0 }}>
        <div>
          <h1>{data.group.name}</h1>
          <p style={{ margin: '2px 0 0', fontSize: 13, color: 'var(--muted)' }}>{data.worksheet_title}</p>
        </div>
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>
          {activeCount} of {data.members.length} active
        </span>
      </div>

      <ProgressStrip current={focusIndex} total={data.total_questions} />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <div style={{ display: 'flex', gap: 10 }}>
          {effectiveIndex > 0 && (
            <button className="btn btn-sm" onClick={() => setViewedIndex(effectiveIndex - 1)}>
              ← Previous question
            </button>
          )}
          {effectiveIndex < focusIndex && (
            <button className="btn btn-sm" onClick={() => setViewedIndex(effectiveIndex + 1)}>
              Next question →
            </button>
          )}
        </div>
        {!isViewingFocus ? (
          <button className="btn btn-sm btn-primary" onClick={() => setViewedIndex(null)}>
            Jump to current question →
          </button>
        ) : (
          <span />
        )}
      </div>

      {isViewingFocus ? (
        <span className="badge badge-success" style={{ marginBottom: 10, display: 'inline-block' }}>
          Question {focusIndex + 1} is in focus
        </span>
      ) : (
        <div className="alert alert-warning" style={{ marginBottom: 14 }}>
          You're viewing Question {effectiveIndex + 1} — the group's in-focus question is Question{' '}
          {focusIndex + 1}. This is just for your own review/practice; nothing here affects the group.
        </div>
      )}

      {isViewingFocus ? (
        <>
          {!isDiscussion && !data.group.is_individual && (
            <TypistBanner
              members={data.members}
              isMeTypist={isMeTypist}
              onGiveUp={handleGiveUp}
              givingUp={givingUp}
            />
          )}

          <div className="panel worksheet-panel">
            <div className="panel-body">
              {actionError && <div className="alert alert-danger">{actionError}</div>}

              <div className="q-label">
                Question {data.question.order_index + 1} — {data.question.title}
              </div>
              <MarkdownContent content={data.question.prompt} />

              {!isDiscussion && (
                <>
                  <CodeEditor
                    code={localCode}
                    readOnly={!isMeTypist}
                    onChange={handleCodeChange}
                    editorLabel={isMeTypist ? "You're editing" : `${currentTypistLabel} is editing`}
                  />
                  {isMeTypist && codeSaveStatus !== 'idle' && (
                    <p style={{ fontSize: 11, color: 'var(--muted)', margin: '4px 0 0' }}>
                      {codeSaveStatus === 'saving' && 'Saving…'}
                      {codeSaveStatus === 'saved' && '✓ Saved'}
                      {codeSaveStatus === 'error' && "⚠ Couldn't save — check your connection"}
                    </p>
                  )}

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
                </>
              )}
            </div>
          </div>

          {!isDiscussion && (
            <ScratchEditor
              key={data.question.id}
              groupId={groupId}
              worksheetId={worksheetId}
              initialCode={data.my_scratch_code}
              predictCall={data.question.predict_call}
              starterCode={data.question.starter_code}
              graderCooldown={data.grader_cooldown}
              isIndividual={data.group.is_individual}
            />
          )}

          <div className="panel">
            <div className="panel-heading">
              <h4>How are you feeling about this question?</h4>
              <span style={{ fontSize: 11, color: 'var(--muted)' }}>seen by your TA</span>
            </div>
            <div className="panel-body">
              <ConfidenceScale value={data.my_rating_value} onRate={handleRate} submitting={ratingSubmitting} />
              <GroupMembersStrip members={data.members} />
              <NextQuestionButton
                ready={data.ready_to_advance}
                allRated={data.all_rated}
                hasPassingRun={data.has_passing_run}
                ratedCount={ratedCount}
                memberCount={data.members.length}
                onAdvance={handleAdvance}
                onForceAdvance={handleForceAdvance}
                advancing={advancing}
              />
            </div>
          </div>
        </>
      ) : (
        <div className="panel worksheet-panel">
          <div className="panel-body">
            {viewedLoading && <p style={{ color: 'var(--muted)' }}>Loading…</p>}
            {viewedError && <div className="alert alert-danger">{viewedError}</div>}
            {viewedQuestion && (
              <PracticeQuestion
                key={viewedQuestion.question_id}
                groupId={groupId}
                worksheetId={worksheetId}
                question={viewedQuestion}
                showPrompt
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
