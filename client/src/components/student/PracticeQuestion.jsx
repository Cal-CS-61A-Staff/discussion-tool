import { useState } from 'react';
import CodeEditor from './CodeEditor.jsx';
import MarkdownContent from './MarkdownContent.jsx';
import TestResultsPanel from './TestResultsPanel.jsx';
import { usePracticeRunner } from '../../hooks/usePracticeRunner.js';

/** One code buffer's practice view — editable for the viewer's own
 * practice, with a "Run tests" button that re-grades it without touching
 * the group's real progress/completed status (server/blueprints/groups.py:
 * POST .../practice-run). Shared between the group's submitted-code block
 * and the personal scratch-code block below, since both need the same
 * editable-code + run + results shape, just against different starting
 * code and with their own independent run state.
 */
function PracticeCodeBlock({ groupId, worksheetId, questionId, initialCode, editorLabel, runLabel, gradingMode }) {
  const [code, setCode] = useState(initialCode || '');
  const { results, running, error, run } = usePracticeRunner(groupId, worksheetId, questionId);
  const canRun = !running && Boolean(code && code.trim());

  return (
    <>
      <CodeEditor code={code} onChange={setCode} editorLabel={editorLabel} />
      {gradingMode !== 'discussion' && (
        <div style={{ marginTop: 8 }}>
          <button type="button" className="btn btn-sm btn-primary" onClick={() => run(code)} disabled={!canRun}>
            {running ? 'Running…' : runLabel}
          </button>
          {error && (
            <div className="alert alert-danger" style={{ marginTop: 10 }}>
              {error}
            </div>
          )}
          <TestResultsPanel results={results} />
        </div>
      )}
    </>
  );
}

/** One question's practice view — shows the group's final submitted code,
 * and, if the viewer ever saved any, their own private scratch code too
 * (server/services/serializers.py: build_group_work). Used by the
 * History page's "View work" section (showPrompt=false, title/code only —
 * the prompt's already implied by "you completed this") and by the live
 * worksheet page's "view a previous question" browsing (showPrompt=true,
 * since there it's the only place the prompt is shown).
 */
export default function PracticeQuestion({ groupId, worksheetId, question, showPrompt }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div className="q-label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span>{question.title}</span>
        <span className={`badge ${question.passed ? 'badge-success' : 'badge-default'}`}>
          {question.passed ? '✓ passed' : question.code ? 'not passing' : 'not attempted'}
        </span>
      </div>
      {showPrompt && <MarkdownContent content={question.prompt} />}
      {question.code != null ? (
        <PracticeCodeBlock
          groupId={groupId}
          worksheetId={worksheetId}
          questionId={question.question_id}
          initialCode={question.code}
          editorLabel="Your code — edit freely to practice"
          runLabel="Run tests"
          gradingMode={question.grading_mode}
        />
      ) : (
        <p style={{ fontSize: 12, color: 'var(--muted)' }}>No code submitted for this question.</p>
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
    </div>
  );
}
