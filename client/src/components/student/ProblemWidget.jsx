import { useEffect, useMemo, useState } from 'react';

/** Renders (and, for graded types, collects an answer to) a non-code
 * question — problem_type is anything other than 'coding'. Used both by
 * the live worksheet page / practice view (with onSubmit) and by the TA
 * editor's preview pane (readOnly).
 *
 * `content` may be the answer-stripped student shape (from
 * server/services/response_grading.py:public_content) or the full
 * authoring shape (in the preview) — the widget reads only the keys that
 * exist in both.
 */

const GRADED_TYPES = new Set([
  'multiple_choice',
  'dropdown',
  'fill_blank_code',
  'fill_blank_markdown',
  'short_answer',
  'counterexample',
]);

const BLANK_MARKER = /\[\[(\d+)\]\]/g;

function optionList(content) {
  return Array.isArray(content?.options) ? content.options : [];
}

function blankCount(content) {
  if (typeof content?.blank_count === 'number') return content.blank_count;
  if (Array.isArray(content?.blanks)) return content.blanks.length;
  const markers = new Set();
  let m;
  const re = new RegExp(BLANK_MARKER);
  while ((m = re.exec(content?.template || '')) !== null) markers.add(m[1]);
  return markers.size;
}

function shortAnswerGraded(content) {
  if (typeof content?.graded === 'boolean') return content.graded;
  return Boolean((content?.answer || '').trim() || (content?.accept || []).length);
}

export default function ProblemWidget({ problemType, content, response, responseCorrect, onSubmit, readOnly, submitting }) {
  const type = problemType || 'coding';
  const graded = GRADED_TYPES.has(type) && (type !== 'short_answer' || shortAnswerGraded(content));

  // Keyed on serialized values, not object identity — this component
  // lives on a page that re-polls every few seconds, and resetting the
  // draft on every poll would wipe what the student is typing. It re-syncs
  // only when the stored answer actually changes (e.g. after a submit).
  const nBlanks = blankCount(content);
  const responseKey = JSON.stringify(response ?? null);
  const initialDraft = useMemo(() => {
    if (type === 'multiple_choice' || type === 'dropdown') {
      return Array.isArray(response) ? response : response == null ? [] : [response];
    }
    if (type === 'fill_blank_code' || type === 'fill_blank_markdown') {
      const base = Array.isArray(response) ? response : [];
      return Array.from({ length: nBlanks }, (_, i) => base[i] ?? '');
    }
    if (type === 'counterexample') {
      const names = (content?.params || []).map((p) => p.name);
      const base = response && typeof response === 'object' ? response : {};
      return Object.fromEntries(names.map((n) => [n, base[n] ?? '']));
    }
    return typeof response === 'string' ? response : '';
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type, nBlanks, responseKey]);

  const [draft, setDraft] = useState(initialDraft);
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    setDraft(initialDraft);
    setDirty(false);
  }, [initialDraft]);

  const update = (next) => {
    setDraft(next);
    setDirty(true);
  };

  // ---- display-only types -------------------------------------------------
  if (type === 'text_markdown') return null; // the prompt above is the content
  if (type === 'image') {
    if (!content?.url) return null;
    return (
      <img
        src={content.url}
        alt={content.alt || ''}
        style={{ maxWidth: content.max_width ? `${content.max_width}px` : '100%', display: 'block', marginTop: 8 }}
      />
    );
  }
  if (type === 'iframe') {
    if (!content?.url) return null;
    return (
      <iframe
        src={content.url}
        title="embedded content"
        style={{ width: '100%', height: `${content.height || 400}px`, border: '1px solid var(--border)', marginTop: 8 }}
      />
    );
  }

  // ---- answer widgets ---------------------------------------------------
  let field = null;

  if (type === 'multiple_choice') {
    const multiple = Boolean(content?.multiple);
    const selected = new Set(draft);
    field = (
      <div className="rows" style={{ gap: 6 }}>
        {optionList(content).map((opt, i) => (
          <label key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}>
            <input
              type={multiple ? 'checkbox' : 'radio'}
              name="mc-option"
              checked={selected.has(i)}
              disabled={readOnly}
              onChange={() => {
                if (multiple) {
                  const next = new Set(selected);
                  next.has(i) ? next.delete(i) : next.add(i);
                  update([...next].sort((a, b) => a - b));
                } else {
                  update([i]);
                }
              }}
            />
            {opt.text}
          </label>
        ))}
      </div>
    );
  } else if (type === 'dropdown') {
    field = (
      <select
        className="form-control"
        style={{ maxWidth: 320 }}
        value={draft.length ? draft[0] : ''}
        disabled={readOnly}
        onChange={(e) => update(e.target.value === '' ? [] : [Number(e.target.value)])}
      >
        <option value="">— choose —</option>
        {optionList(content).map((opt, i) => (
          <option key={i} value={i}>
            {opt.text}
          </option>
        ))}
      </select>
    );
  } else if (type === 'fill_blank_code' || type === 'fill_blank_markdown') {
    const segments = String(content?.template || '').split(BLANK_MARKER);
    // split with a capturing group yields [text, n, text, n, text, ...]
    field = (
      <div
        style={{
          whiteSpace: 'pre-wrap',
          fontFamily: type === 'fill_blank_code' ? 'var(--mono, monospace)' : 'inherit',
          fontSize: 14,
          lineHeight: 1.9,
        }}
      >
        {segments.map((seg, idx) => {
          if (idx % 2 === 1) {
            const blankIndex = Number(seg) - 1;
            return (
              <input
                key={idx}
                className="form-control code"
                style={{ display: 'inline-block', width: 120, padding: '2px 6px', margin: '0 3px' }}
                value={draft[blankIndex] ?? ''}
                disabled={readOnly}
                onChange={(e) => {
                  const next = [...draft];
                  next[blankIndex] = e.target.value;
                  update(next);
                }}
              />
            );
          }
          return <span key={idx}>{seg}</span>;
        })}
      </div>
    );
  } else if (type === 'short_answer') {
    field = (
      <input
        className="form-control"
        style={{ maxWidth: 420 }}
        value={draft}
        disabled={readOnly}
        onChange={(e) => update(e.target.value)}
        placeholder="Your answer"
      />
    );
  } else if (type === 'counterexample') {
    const names = (content?.params || []).map((p) => p.name);
    field = (
      <div>
        {content?.buggy_code ? (
          <pre className="code-editor-wrap" style={{ padding: 10, margin: '0 0 10px', color: '#eee' }}>
            <code className="code">{content.buggy_code}</code>
          </pre>
        ) : null}
        {content?.constraints ? (
          <p style={{ fontSize: 12, color: 'var(--muted)', margin: '0 0 8px' }}>
            Inputs must satisfy <code className="code">{content.constraints}</code>.
          </p>
        ) : null}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {names.map((n) => (
            <label key={n} style={{ fontSize: 13 }}>
              {n}{' = '}
              <input
                className="form-control code"
                style={{ display: 'inline-block', width: 90, padding: '2px 6px' }}
                value={(draft && draft[n]) || ''}
                disabled={readOnly}
                onChange={(e) => update({ ...draft, [n]: e.target.value })}
              />
            </label>
          ))}
        </div>
      </div>
    );
  } else if (type === 'plain_text') {
    field = (
      <>
        <textarea
          className="form-control"
          rows={5}
          value={draft}
          disabled={readOnly}
          onChange={(e) => update(e.target.value)}
        />
        {content?.min_length > 0 && (
          <p style={{ fontSize: 11, color: 'var(--muted)', margin: '4px 0 0' }}>
            {draft.trim().length}/{content.min_length} characters minimum
          </p>
        )}
      </>
    );
  } else {
    return null;
  }

  const meetsMin =
    type !== 'plain_text' || !content?.min_length || String(draft).trim().length >= content.min_length;
  let hasAnswer;
  if (['multiple_choice', 'dropdown', 'fill_blank_code', 'fill_blank_markdown'].includes(type)) {
    hasAnswer = Array.isArray(draft) && draft.some((v) => v !== '' && v != null);
  } else if (type === 'counterexample') {
    hasAnswer = draft && Object.values(draft).every((v) => String(v).trim().length > 0);
  } else {
    hasAnswer = String(draft).trim().length > 0;
  }

  const submitLabel = submitting
    ? type === 'counterexample'
      ? 'Checking…'
      : 'Submitting…'
    : graded
      ? 'Submit answer'
      : 'Save answer';

  return (
    <div className="problem-widget" style={{ marginTop: 10 }}>
      {field}
      {!readOnly && onSubmit && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 12 }}>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={submitting || !dirty || !hasAnswer || !meetsMin}
            onClick={() => onSubmit(draft)}
          >
            {submitLabel}
          </button>
          {!dirty && response != null && graded && responseCorrect === true && (
            <span className="badge badge-success">
              {type === 'counterexample' ? '✓ that breaks it!' : '✓ correct'}
            </span>
          )}
          {!dirty && response != null && graded && responseCorrect === false && (
            <span className="badge badge-default">
              {type === 'counterexample' ? '✗ the code handles that — keep looking' : '✗ not correct yet'}
            </span>
          )}
          {!dirty && response != null && !graded && <span className="badge badge-default">answer saved</span>}
        </div>
      )}
    </div>
  );
}
