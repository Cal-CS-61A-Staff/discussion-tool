import { useState } from 'react';
import CodeEditor from './CodeEditor.jsx';
import ConfidenceScale from './ConfidenceScale.jsx';
import MarkdownContent from './MarkdownContent.jsx';
import PredictionPanel from './PredictionPanel.jsx';
import ProblemWidget from './ProblemWidget.jsx';
import PythonTutorPanel from './PythonTutorPanel.jsx';
import TestResultsPanel from './TestResultsPanel.jsx';
import * as groupsApi from '../../api/groups.js';
import { usePracticeRunner } from '../../hooks/usePracticeRunner.js';

/** One code buffer's practice view — editable for the viewer's own
 * practice, with the same "Run tests" + results the live question has, all
 * re-graded without touching the group's real progress/completed status
 * (server/blueprints/groups.py: POST .../practice-run). Shared between the
 * group's submitted-code block and the personal scratch-code block below.
 */
function PracticeCodeBlock({ groupId, worksheetId, questionId, initialCode, editorLabel, runLabel, gradingMode }) {
  const [code, setCode] = useState(initialCode || '');
  const { results, running, error, run, remainingSeconds, cooldownSeconds } = usePracticeRunner(
    groupId,
    worksheetId,
    questionId
  );

  const onCooldown = remainingSeconds > 0;
  const canRun = !running && !onCooldown && Boolean(code && code.trim());
  const ringCircumference = 2 * Math.PI * 6.5;
  const ringOffset =
    cooldownSeconds > 0 ? ringCircumference * (1 - remainingSeconds / cooldownSeconds) : ringCircumference;

  return (
    <>
      <CodeEditor code={code} onChange={setCode} editorLabel={editorLabel} />
      {gradingMode !== 'discussion' && (
        <div className="predict-row" style={{ marginTop: 14 }}>
          <button type="button" className="btn btn-primary run-btn" onClick={() => run(code, '')} disabled={!canRun}>
            {onCooldown && (
              <svg className="cooldown-ring" viewBox="0 0 16 16">
                <circle cx="8" cy="8" r="6.5" strokeDasharray={ringCircumference} strokeDashoffset={ringOffset} />
              </svg>
            )}
            {onCooldown ? `Wait ${remainingSeconds}s` : running ? 'Running…' : runLabel}
          </button>
          {error && (
            <div className="alert alert-danger" style={{ marginTop: 10, width: '100%' }}>
              {error}
            </div>
          )}
          <div style={{ width: '100%' }}>
            <TestResultsPanel results={results} />
          </div>
        </div>
      )}
    </>
  );
}

/** One question's practice view — shows the group's final submitted code
 * (falling back to the question's starter code if the group never
 * submitted a run for it, e.g. it's the current in-progress question being
 * reviewed mid-worksheet), and, if the viewer ever saved any, their own
 * private scratch code too (server/services/serializers.py:
 * build_group_work). Used by WorkBrowserPage's click-through "View work"
 * (showPrompt=true) and by the live worksheet page's "view a previous
 * question" browsing (showPrompt=true) — deliberately kept at full parity
 * with the live in-focus question (code editor, prediction quiz, "Run
 * tests", and the confidence rating below) rather than a read-only replay,
 * since re-visiting a question is exactly when you might want to try it
 * again or update how you felt about it.
 *
 * Pass a React `key` of `question.question_id` at the call site so this
 * component remounts (and its rating/code state resets) when the viewed
 * question changes.
 */
export default function PracticeQuestion({ groupId, worksheetId, question, showPrompt }) {
  const [ratingValue, setRatingValue] = useState(question.my_rating ?? null);
  const [ratingSubmitting, setRatingSubmitting] = useState(false);
  const [responseSubmitting, setResponseSubmitting] = useState(false);
  const [response, setResponse] = useState(question.group_response ?? null);
  const [responseCorrect, setResponseCorrect] = useState(question.group_response_correct ?? null);
  const [prediction, setPrediction] = useState(question.prediction ?? null);
  const [predictionSubmitting, setPredictionSubmitting] = useState(false);

  const isCoding = (question.problem_type || 'coding') === 'coding';

  const handleSubmitPrediction = async (text) => {
    setPredictionSubmitting(true);
    try {
      const res = await groupsApi.submitPrediction(groupId, worksheetId, question.question_id, text);
      setPrediction((p) => ({ ...p, group_answer: text, group_correct: res.is_correct ?? null }));
    } catch {
      // Best-effort — reviewing a past question doesn't gate anything.
    } finally {
      setPredictionSubmitting(false);
    }
  };

  const handleSubmitResponse = async (value) => {
    setResponseSubmitting(true);
    try {
      const res = await groupsApi.submitResponse(groupId, worksheetId, question.question_id, value);
      setResponse(value);
      setResponseCorrect(res.is_correct ?? null);
    } catch {
      // Best-effort — reviewing a past question doesn't gate anything.
    } finally {
      setResponseSubmitting(false);
    }
  };

  const handleRate = async (value) => {
    setRatingSubmitting(true);
    try {
      await groupsApi.submitRating(groupId, worksheetId, value, question.question_id);
      setRatingValue(value);
    } catch {
      // Best-effort — reviewing/re-rating a past question doesn't gate
      // anything, so a transient failure here just means "try again".
    } finally {
      setRatingSubmitting(false);
    }
  };

  return (
    <div style={{ marginBottom: 16 }}>
      <div className="q-label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span>{question.title}</span>
        <span className={`badge ${question.passed || responseCorrect ? 'badge-success' : 'badge-default'}`}>
          {!isCoding
            ? responseCorrect
              ? '✓ correct'
              : response != null
                ? 'answered'
                : 'not answered'
            : question.passed
              ? '✓ passed'
              : question.code
                ? 'not passing'
                : 'not attempted'}
        </span>
      </div>
      {showPrompt && <MarkdownContent content={question.prompt} />}
      {!isCoding && (
        <ProblemWidget
          problemType={question.problem_type}
          content={question.content}
          response={response}
          responseCorrect={responseCorrect}
          onSubmit={handleSubmitResponse}
          submitting={responseSubmitting}
        />
      )}
      {isCoding && question.grading_mode !== 'discussion' && (
        <PracticeCodeBlock
          groupId={groupId}
          worksheetId={worksheetId}
          questionId={question.question_id}
          initialCode={question.code ?? question.starter_code}
          editorLabel="Your code — edit freely to practice"
          runLabel="Run tests"
          gradingMode={question.grading_mode}
        />
      )}
      <PythonTutorPanel code={question.python_tutor_code} />
      {prediction && (
        <PredictionPanel
          prediction={prediction}
          onSubmit={handleSubmitPrediction}
          submitting={predictionSubmitting}
        />
      )}
      {question.scratch_code != null && (
        <div className="panel" style={{ marginTop: 16 }}>
          <div className="panel-heading">
            <h4>Your scratch work</h4>
            <span style={{ fontSize: 11, color: 'var(--muted)' }}>private — not shared with your group</span>
          </div>
          <div className="panel-body">
            <PracticeCodeBlock
              groupId={groupId}
              worksheetId={worksheetId}
              questionId={question.question_id}
              initialCode={question.scratch_code}
              editorLabel="scratch"
              runLabel="Run tests on my scratch code"
              gradingMode={question.grading_mode}
            />
          </div>
        </div>
      )}
      <div className="panel" style={{ marginTop: 16 }}>
        <div className="panel-heading">
          <h4>How are you feeling about this question?</h4>
          <span style={{ fontSize: 11, color: 'var(--muted)' }}>seen by your TA</span>
        </div>
        <div className="panel-body">
          <ConfidenceScale value={ratingValue} onRate={handleRate} submitting={ratingSubmitting} />
        </div>
      </div>
    </div>
  );
}
