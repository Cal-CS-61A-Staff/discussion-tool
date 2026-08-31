/** The authoring sub-form for a non-code question type. `content` is the
 * full authoring shape (with answers); `onChange` gets the next content
 * object. See server/services/response_grading.py:validate_content for
 * what the server expects.
 */

export const PROBLEM_TYPE_DEFAULT_CONTENT = {
  multiple_choice: () => ({
    options: [
      { text: '', correct: false },
      { text: '', correct: false },
    ],
    multiple: false,
  }),
  dropdown: () => ({
    options: [
      { text: '', correct: true },
      { text: '', correct: false },
    ],
  }),
  fill_blank_code: () => ({ template: '', blanks: [] }),
  fill_blank_markdown: () => ({ template: '', blanks: [] }),
  short_answer: () => ({ answer: '', accept: [], case_sensitive: false }),
  prediction: () => ({ setup: '', doctest: '', items: [] }),
  text_markdown: () => ({}),
  plain_text: () => ({ min_length: 0 }),
  image: () => ({ url: '', alt: '', max_width: '' }),
  iframe: () => ({ url: '', height: 400 }),
};

const BLANK_MARKER = /\[\[(\d+)\]\]/g;

const joinAccept = (arr) => (Array.isArray(arr) ? arr.join(', ') : '');
const splitAccept = (str) =>
  str
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);

function OptionsEditor({ content, onChange, single }) {
  const options = content.options || [];
  const setOptions = (next) => onChange({ ...content, options: next });

  const setCorrect = (i) => {
    if (single) {
      setOptions(options.map((o, idx) => ({ ...o, correct: idx === i })));
    } else {
      setOptions(options.map((o, idx) => (idx === i ? { ...o, correct: !o.correct } : o)));
    }
  };

  return (
    <div className="form-group" style={{ marginBottom: 0 }}>
      <label>Answer options {single ? '(pick the one correct answer)' : '(check every correct answer)'}</label>
      <div className="rows" style={{ gap: 6 }}>
        {options.map((opt, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input
              type={single ? 'radio' : 'checkbox'}
              name="pt-option-correct"
              checked={Boolean(opt.correct)}
              onChange={() => setCorrect(i)}
              title="Correct?"
            />
            <input
              className="form-control"
              value={opt.text}
              placeholder={`Option ${i + 1}`}
              onChange={(e) => setOptions(options.map((o, idx) => (idx === i ? { ...o, text: e.target.value } : o)))}
            />
            <button
              type="button"
              className="btn btn-sm"
              disabled={options.length <= 2}
              onClick={() => setOptions(options.filter((_, idx) => idx !== i))}
            >
              Remove
            </button>
          </div>
        ))}
      </div>
      <button
        type="button"
        className="btn btn-sm"
        style={{ marginTop: 8 }}
        onClick={() => setOptions([...options, { text: '', correct: false }])}
      >
        + Add option
      </button>
    </div>
  );
}

function FillBlankEditor({ content, onChange, code }) {
  const template = content.template || '';
  const markers = [...new Set([...template.matchAll(BLANK_MARKER)].map((m) => Number(m[1])))].sort((a, b) => a - b);
  const blanks = content.blanks || [];

  const syncedBlanks = markers.map((_, i) => blanks[i] || { answer: '', accept: [], case_sensitive: false });

  const setTemplate = (value) => {
    const nextMarkers = [...new Set([...value.matchAll(BLANK_MARKER)].map((m) => Number(m[1])))].sort((a, b) => a - b);
    const next = nextMarkers.map((_, i) => blanks[i] || { answer: '', accept: [], case_sensitive: false });
    onChange({ ...content, template: value, blanks: next });
  };
  const setBlank = (i, patch) => {
    const next = syncedBlanks.map((b, idx) => (idx === i ? { ...b, ...patch } : b));
    onChange({ ...content, blanks: next });
  };

  return (
    <>
      <div className="form-group">
        <label htmlFor="pt-template">Template — mark each blank with [[1]], [[2]], … in order</label>
        <textarea
          id="pt-template"
          className={`form-control ${code ? 'code' : ''}`}
          rows={code ? 6 : 4}
          value={template}
          onChange={(e) => setTemplate(e.target.value)}
          placeholder={code ? 'def area(r):\n    return [[1]] * r ** [[2]]' : 'The time complexity is [[1]].'}
        />
      </div>
      {markers.length === 0 && (
        <p style={{ fontSize: 12, color: 'var(--muted)' }}>Add a [[1]] marker to the template to configure its answer.</p>
      )}
      {markers.map((n, i) => (
        <div key={n} className="form-group" style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <div style={{ flex: 1 }}>
            <label>Blank [[{n}]] answer</label>
            <input
              className="form-control code"
              value={syncedBlanks[i].answer}
              onChange={(e) => setBlank(i, { answer: e.target.value })}
            />
          </div>
          <div style={{ flex: 1 }}>
            <label>Also accept (comma-separated)</label>
            <input
              className="form-control"
              value={joinAccept(syncedBlanks[i].accept)}
              onChange={(e) => setBlank(i, { accept: splitAccept(e.target.value) })}
            />
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, paddingBottom: 8 }}>
            <input
              type="checkbox"
              checked={Boolean(syncedBlanks[i].case_sensitive)}
              onChange={(e) => setBlank(i, { case_sensitive: e.target.checked })}
            />
            case-sensitive
          </label>
        </div>
      ))}
    </>
  );
}

export default function ProblemTypeEditor({ type, content, onChange }) {
  const c = content || {};

  if (type === 'multiple_choice') {
    return (
      <>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, marginBottom: 10 }}>
          <input
            type="checkbox"
            checked={Boolean(c.multiple)}
            onChange={(e) => onChange({ ...c, multiple: e.target.checked })}
          />
          Allow more than one correct answer
        </label>
        <OptionsEditor content={c} onChange={onChange} single={!c.multiple} />
      </>
    );
  }

  if (type === 'dropdown') {
    return <OptionsEditor content={c} onChange={onChange} single />;
  }

  if (type === 'fill_blank_code' || type === 'fill_blank_markdown') {
    return <FillBlankEditor content={c} onChange={onChange} code={type === 'fill_blank_code'} />;
  }

  if (type === 'short_answer') {
    return (
      <>
        <div className="form-group">
          <label htmlFor="pt-answer">Model answer</label>
          <input
            id="pt-answer"
            className="form-control"
            value={c.answer || ''}
            onChange={(e) => onChange({ ...c, answer: e.target.value })}
          />
          <p style={{ fontSize: 12, color: 'var(--muted)', margin: '4px 0 0' }}>
            Leave blank for an ungraded written prompt (stored, not auto-checked).
          </p>
        </div>
        <div className="form-group">
          <label htmlFor="pt-accept">Also accept (comma-separated)</label>
          <input
            id="pt-accept"
            className="form-control"
            value={joinAccept(c.accept)}
            onChange={(e) => onChange({ ...c, accept: splitAccept(e.target.value) })}
          />
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
          <input
            type="checkbox"
            checked={Boolean(c.case_sensitive)}
            onChange={(e) => onChange({ ...c, case_sensitive: e.target.checked })}
          />
          Case-sensitive
        </label>
      </>
    );
  }

  if (type === 'prediction') {
    const itemCount = (String(c.doctest || '').match(/^\s*>>>/gm) || []).length;
    return (
      <>
        <div className="form-group">
          <label htmlFor="pt-pred-setup">Setup code (optional)</label>
          <p style={{ fontSize: 12, color: 'var(--muted)', margin: '2px 0 6px' }}>
            Runs before every snippet. Hidden from students.
          </p>
          <textarea
            id="pt-pred-setup"
            className="form-control code"
            rows={3}
            value={c.setup || ''}
            onChange={(e) => onChange({ ...c, setup: e.target.value })}
          />
        </div>
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label htmlFor="pt-pred-doctest">Prediction items</label>
          <p style={{ fontSize: 12, color: 'var(--muted)', margin: '2px 0 6px' }}>
            One <code className="code">&gt;&gt;&gt;</code> example per item, with its expected output on the line(s)
            below — just like a doctest. Students are shown the code for one randomly-chosen item and predict its
            output; the expected values are checked against the sandbox when you save and never shown to students.
          </p>
          <textarea
            id="pt-pred-doctest"
            className="form-control code"
            rows={8}
            value={c.doctest || ''}
            onChange={(e) => onChange({ ...c, doctest: e.target.value })}
            placeholder={'>>> 1 + 1\n2\n>>> sorted([3, 1, 2])\n[1, 2, 3]'}
          />
          <p style={{ fontSize: 12, color: 'var(--muted)', margin: '6px 0 0' }}>
            {itemCount} prediction item{itemCount === 1 ? '' : 's'} detected.
          </p>
        </div>
      </>
    );
  }

  if (type === 'text_markdown') {
    return (
      <p style={{ fontSize: 13, color: 'var(--muted)', margin: 0 }}>
        Nothing to configure — the problem description above is shown to students as the content, and there's no
        answer to collect.
      </p>
    );
  }

  if (type === 'plain_text') {
    return (
      <div className="form-group" style={{ marginBottom: 0, maxWidth: 260 }}>
        <label htmlFor="pt-minlen">Minimum length (characters, 0 for none)</label>
        <input
          id="pt-minlen"
          type="number"
          min={0}
          className="form-control"
          value={c.min_length ?? 0}
          onChange={(e) => onChange({ ...c, min_length: Number(e.target.value) || 0 })}
        />
        <p style={{ fontSize: 12, color: 'var(--muted)', margin: '4px 0 0' }}>
          Free-response — stored for the TA to read, never auto-graded.
        </p>
      </div>
    );
  }

  if (type === 'image') {
    return (
      <>
        <div className="form-group">
          <label htmlFor="pt-img-url">Image URL</label>
          <input
            id="pt-img-url"
            className="form-control"
            value={c.url || ''}
            onChange={(e) => onChange({ ...c, url: e.target.value })}
          />
        </div>
        <div className="form-group">
          <label htmlFor="pt-img-alt">Alt text</label>
          <input
            id="pt-img-alt"
            className="form-control"
            value={c.alt || ''}
            onChange={(e) => onChange({ ...c, alt: e.target.value })}
          />
        </div>
        <div className="form-group" style={{ marginBottom: 0, maxWidth: 220 }}>
          <label htmlFor="pt-img-w">Max width (px, optional)</label>
          <input
            id="pt-img-w"
            type="number"
            min={0}
            className="form-control"
            value={c.max_width ?? ''}
            onChange={(e) => onChange({ ...c, max_width: e.target.value === '' ? '' : Number(e.target.value) })}
          />
        </div>
      </>
    );
  }

  if (type === 'iframe') {
    return (
      <>
        <div className="form-group">
          <label htmlFor="pt-if-url">Embed URL</label>
          <input
            id="pt-if-url"
            className="form-control"
            value={c.url || ''}
            onChange={(e) => onChange({ ...c, url: e.target.value })}
          />
        </div>
        <div className="form-group" style={{ marginBottom: 0, maxWidth: 220 }}>
          <label htmlFor="pt-if-h">Height (px)</label>
          <input
            id="pt-if-h"
            type="number"
            min={100}
            className="form-control"
            value={c.height ?? 400}
            onChange={(e) => onChange({ ...c, height: Number(e.target.value) || 400 })}
          />
        </div>
      </>
    );
  }

  return null;
}
