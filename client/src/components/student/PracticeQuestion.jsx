import { useState } from 'react';
import CodeEditor from './CodeEditor.jsx';
import ConfidenceScale from './ConfidenceScale.jsx';
import GraderFeedbackPanel from './GraderFeedbackPanel.jsx';
import MarkdownContent from './MarkdownContent.jsx';
import ProblemWidget from './ProblemWidget.jsx';
import TestResultsPanel from './TestResultsPanel.jsx';
import * as groupsApi from '../../api/groups.js';
import { usePracticeRunner } from '../../hooks/usePracticeRunner.js';

/** One code buffer's practice view — editable for the viewer's own
 * practice, with the same prediction quiz + "Run tests" + results the live
 * question has, all re-graded without touching the group's real progress/
 * completed status (server/blueprints/groups.py: POST .../practice-run).
 * Shared between the group's submitted-code block and the personal
 * scratch-code block below, since both need the same shape, just against
 * different starting code and with their own independent run state.
 */
function PracticeCodeBlock({ groupId, worksheetId, questionId, initialCode, predictCall, editorLabel, runLabel, gradingMode }) {
  const [code, setCode] = useState(initialCode || '');
  const [prediction, setPrediction] = useState('');
  const { results, running, error, run, remainingSeconds, cooldownSeconds } = usePracticeRunner(
    groupId,
    worksheetId,
    questionId
  );

  const onCooldown = remainingSeconds > 0;
  const canRun = !running && !onCooldown && Boolean(code && code.trim()) && Boolean(prediction.trim());
  const ringCircumference = 2 * Math.PI * 6.5;
  const ringOffset =
    cooldownSeconds > 0 ? ringCircumference * (1 - remainingSeconds / cooldownSeconds) : ringCircumference;

  const question = predictCall ? (
    <>
      What do you think <code className="code">{predictCall}</code> will output?
    </>
  ) : (
    'What do you think this code will output?'
  );

  return (
    <>
      <CodeEditor code={code} onChange={setCode} editorLabel={editorLabel} />
      {gradingMode !== 'discussion' && (
        <div className="predict-row" style={{ marginTop: 14 }}>
          <div className="predict-field form-group" style={{ marginBottom: 0 }}>
            <label htmlFor={`practice-prediction-${questionId}-${editorLabel}`}>{question}</label>
            <textarea
              id={`practice-prediction-${questionId}-${editorLabel}`}
              className="form-control code"
              rows={3}
              value={prediction}
              onChange={(e) => setPrediction(e.target.value)}
              placeholder="Type your prediction before running"
            />
          </div>
          <button type="button" className="btn btn-primary run-btn" onClick={() => run(code, prediction.trim())} disabled={!canRun}>
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
            <GraderFeedbackPanel feedback={results?.prediction_feedback} />
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

  const isCoding = (question.problem_type || 'coding') === 'coding';

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
          predictCall={question.predict_call}
          editorLabel="Your code — edit freely to practice"
          runLabel="Run tests"
          gradingMode={question.grading_mode}
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
              predictCall={question.predict_call}
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
