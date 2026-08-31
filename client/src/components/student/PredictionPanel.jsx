import { useEffect, useState } from 'react';
import MarkdownContent from './MarkdownContent.jsx';

/** The optional prediction prompt on a question (any problem_type). One
 * shared answer per group; it gates advancing. `prediction` is the
 * answer-stripped object from the /state payload:
 *   output  -> { mode, setup, item: {code} | null, group_answer, group_correct }
 *   written -> { mode, prompt, group_answer, group_correct }
 */
export default function PredictionPanel({ prediction, onSubmit, submitting, readOnly }) {
  const initial = typeof prediction?.group_answer === 'string' ? prediction.group_answer : '';
  const [draft, setDraft] = useState(initial);
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    setDraft(initial);
    setDirty(false);
  }, [initial]);

  if (!prediction) return null;
  const output = prediction.mode !== 'written';
  const answered = !dirty && prediction.group_answer != null;

  return (
    <div className="panel" style={{ marginTop: 14 }}>
      <div className="panel-heading">
        <h4>{output ? 'Predict the output' : 'Before you move on'}</h4>
        <span style={{ fontSize: 11, color: 'var(--muted)' }}>your group answers this to continue</span>
      </div>
      <div className="panel-body">
        {output ? (
          <>
            {prediction.setup ? (
              <pre className="code-editor-wrap" style={{ padding: 10, margin: '0 0 8px', color: '#eee' }}>
                <code className="code">{prediction.setup}</code>
              </pre>
            ) : null}
            {prediction.item ? (
              <pre className="code-editor-wrap" style={{ padding: 10, margin: 0, color: '#eee' }}>
                <code className="code">{prediction.item.code}</code>
              </pre>
            ) : (
              <p style={{ color: 'var(--muted)', fontSize: 13 }}>Preparing your prediction…</p>
            )}
            <label style={{ display: 'block', fontSize: 13, margin: '10px 0 4px' }}>What does this display?</label>
          </>
        ) : (
          <MarkdownContent content={prediction.prompt || ''} />
        )}
        <textarea
          className={`form-control ${output ? 'code' : ''}`}
          rows={output ? 3 : 4}
          value={draft}
          disabled={readOnly || (output && !prediction.item)}
          onChange={(e) => {
            setDraft(e.target.value);
            setDirty(true);
          }}
          placeholder={output ? 'Type the exact output' : 'A sentence or two…'}
        />
        {!readOnly && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 10 }}>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={submitting || !dirty || !draft.trim() || (output && !prediction.item)}
              onClick={() => onSubmit(draft)}
            >
              {submitting ? 'Submitting…' : 'Submit prediction'}
            </button>
            {answered && output && prediction.group_correct === true && (
              <span className="badge badge-success">✓ correct</span>
            )}
            {answered && output && prediction.group_correct === false && (
              <span className="badge badge-default">✗ not correct yet</span>
            )}
            {answered && !output && <span className="badge badge-default">answer saved</span>}
          </div>
        )}
      </div>
    </div>
  );
}
