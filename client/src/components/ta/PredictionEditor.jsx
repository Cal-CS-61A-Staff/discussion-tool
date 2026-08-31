/** The optional "prediction prompt" panel — available on every problem
 * type. `prediction` is null (no prompt) or
 *   { mode: 'output', setup, doctest }  |  { mode: 'written', prompt }
 * When set it gates advancing. See server/services/response_grading.py:
 * validate_prediction.
 */
export default function PredictionEditor({ prediction, onChange }) {
  const enabled = prediction != null;
  const mode = prediction?.mode || 'output';

  const setMode = (next) =>
    onChange(next === 'written' ? { mode: 'written', prompt: prediction?.prompt || '' } : { mode: 'output', setup: prediction?.setup || '', doctest: prediction?.doctest || '' });

  const itemCount = (String(prediction?.doctest || '').match(/^\s*>>>/gm) || []).length;

  return (
    <div className="panel">
      <div className="panel-heading">
        <h4>Prediction prompt (optional)</h4>
        <span style={{ fontSize: 11, color: 'var(--muted)' }}>gates advancing when set</span>
      </div>
      <div className="panel-body">
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, marginBottom: enabled ? 12 : 0 }}>
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => onChange(e.target.checked ? { mode: 'output', setup: '', doctest: '' } : null)}
          />
          Ask the group to make a prediction before they can move on
        </label>

        {enabled && (
          <>
            <div className="form-group" style={{ display: 'flex', gap: 16 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                <input type="radio" checked={mode === 'output'} onChange={() => setMode('output')} />
                Predict the output of a snippet
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                <input type="radio" checked={mode === 'written'} onChange={() => setMode('written')} />
                Written reflection
              </label>
            </div>

            {mode === 'written' ? (
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label htmlFor="pred-prompt">Reflection prompt</label>
                <textarea
                  id="pred-prompt"
                  className="form-control"
                  rows={3}
                  value={prediction.prompt || ''}
                  onChange={(e) => onChange({ ...prediction, prompt: e.target.value })}
                  placeholder="e.g. In one sentence, describe the process your group implemented."
                />
              </div>
            ) : (
              <>
                <div className="form-group">
                  <label htmlFor="pred-setup">Setup code (optional)</label>
                  <p style={{ fontSize: 12, color: 'var(--muted)', margin: '2px 0 6px' }}>
                    Runs before every snippet. Hidden from students.
                  </p>
                  <textarea
                    id="pred-setup"
                    className="form-control code"
                    rows={3}
                    value={prediction.setup || ''}
                    onChange={(e) => onChange({ ...prediction, setup: e.target.value })}
                  />
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label htmlFor="pred-doctest">Prediction items</label>
                  <p style={{ fontSize: 12, color: 'var(--muted)', margin: '2px 0 6px' }}>
                    One <code className="code">&gt;&gt;&gt;</code> example per item with its expected output below —
                    like a doctest. Students see one at random and predict its output; the expected values are
                    verified against the sandbox when you save.
                  </p>
                  <textarea
                    id="pred-doctest"
                    className="form-control code"
                    rows={7}
                    value={prediction.doctest || ''}
                    onChange={(e) => onChange({ ...prediction, doctest: e.target.value })}
                    placeholder={'>>> race(5, 7)\n7\n>>> race(2, 4)\n10'}
                  />
                  <p style={{ fontSize: 12, color: 'var(--muted)', margin: '6px 0 0' }}>
                    {itemCount} prediction item{itemCount === 1 ? '' : 's'} detected.
                  </p>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
