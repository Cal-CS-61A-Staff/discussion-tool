import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import PracticeQuestion from '../components/student/PracticeQuestion.jsx';
import ProgressStrip from '../components/student/ProgressStrip.jsx';
import * as groupsApi from '../api/groups.js';

/** Read-only, question-by-question replay of a group's work on one
 * assignment — "View work" from the Assignments page lands here instead of
 * dumping every question inline in a list, so it matches the same
 * click-through feel as actually working the assignment (server/services/
 * serializers.py:build_group_work already returns only the unlocked
 * questions, whether the assignment is still in progress or fully done).
 * `index` can go one past the last real question — that's the "you've seen
 * everything" screen below, not a question.
 */
export default function WorkBrowserPage() {
  const { groupId, worksheetId } = useParams();
  const navigate = useNavigate();

  const [work, setWork] = useState(null);
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    groupsApi
      .getGroupWork(groupId, worksheetId)
      .then((data) => setWork(data))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [groupId, worksheetId]);

  if (loading) return <div className="page-loading">Loading…</div>;

  const goBack = () => navigate(-1);
  const backToAssignments = () => navigate('/assignments');

  if (error) {
    return (
      <div>
        <div className="alert alert-danger">{error}</div>
        <a
          href="/"
          onClick={(e) => {
            e.preventDefault();
            goBack();
          }}
        >
          ← Back
        </a>
      </div>
    );
  }

  if (!work || work.questions.length === 0) {
    return <p style={{ color: 'var(--muted)' }}>Nothing to show yet.</p>;
  }

  const total = work.questions.length;
  const passedCount = work.questions.filter((q) => q.passed).length;
  const done = index === total;

  return (
    <div>
      <div className="breadcrumb-row">
        <a
          href="/"
          onClick={(e) => {
            e.preventDefault();
            goBack();
          }}
        >
          ← Back
        </a>
        <span>·</span>
        <span>{work.worksheet_title}</span>
      </div>

      {done ? (
        <div className="panel" style={{ marginTop: 16, textAlign: 'center' }}>
          <div className="panel-body" style={{ padding: '40px 20px' }}>
            <div style={{ fontSize: 40, marginBottom: 8 }}>🎉</div>
            <h2 style={{ margin: '0 0 4px' }}>You've reviewed every question</h2>
            <p style={{ color: 'var(--muted)', marginBottom: 24 }}>
              {passedCount} of {total} passed on {work.worksheet_title}.
            </p>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
              <button type="button" className="btn" onClick={() => setIndex(total - 1)}>
                ← Back to last question
              </button>
              <button type="button" className="btn btn-primary" onClick={backToAssignments}>
                Back to assignments
              </button>
            </div>
          </div>
        </div>
      ) : (
        <>
          <ProgressStrip current={index} total={total} completed={passedCount} />

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            {index > 0 ? (
              <button type="button" className="btn btn-sm" onClick={() => setIndex(index - 1)}>
                ← Previous question
              </button>
            ) : (
              <span />
            )}
            <button type="button" className="btn btn-sm btn-primary" onClick={() => setIndex(index + 1)}>
              {index === total - 1 ? 'Finish →' : 'Next question →'}
            </button>
          </div>

          <PracticeQuestion
            key={work.questions[index].question_id}
            groupId={groupId}
            worksheetId={worksheetId}
            question={work.questions[index]}
            showPrompt
          />
        </>
      )}
    </div>
  );
}
