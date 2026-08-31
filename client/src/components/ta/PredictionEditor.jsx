/** The optional "prediction prompt" panel — available on every problem
 * type. `prediction` is null (no prompt) or
 *   { mode: 'output', setup, calls }  |  { mode: 'written', prompt }
 * For 'output', `calls` is one call expression per line (e.g. fizzbuzz(5));
 * each is run against the question's own code at save time and the output
 * captured as the expected answer. When set, the prediction gates
 * advancing. See server/services/response_grading.py:validate_prediction
 * and server/blueprints/admin.py:_resolve_prediction_items.
 */
export default function PredictionEditor({ prediction, onChange }) {
  const enabled = prediction != null;
  const mode = prediction?.mode || 'output';
  const callsText = Array.isArray(prediction?.calls)
    ? prediction.calls.join('\n')
    : prediction?.calls || '';
  const callCount = callsText.split('\n').filter((l) => l.trim()).length;

  const setMode = (next) =>
    onChange(
      next === 'written'
        ? { mode: 'written', prompt: prediction?.prompt || '' }
        : { mode: 'output', setup: prediction?.setup || '', calls: callsText }
    );

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
            onChange={(e) => onChange(e.target.checked ? { mode: 'output', setup: '', calls: '' } : null)}
          />
          Ask the group to make a prediction before they can move on
        </label>

        {enabled && (
          <>
            <div className="form-group" style={{ display: 'flex', gap: 16 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                <input type="radio" checked={mode === 'output'} onChange={() => setMode('output')} />
                Predict the output of a call
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
                  <label htmlFor="pred-calls">Calls to predict — one per line</label>
                  <p style={{ fontSize: 12, color: 'var(--muted)', margin: '2px 0 6px' }}>
                    Each is run against this question's code (its reference solution + setup) when you save, and the
                    output becomes the answer. Students see one at random and predict what it displays.
                  </p>
                  <textarea
                    id="pred-calls"
                    className="form-control code"
                    rows={4}
                    value={callsText}
                    onChange={(e) => onChange({ ...prediction, calls: e.target.value })}
                    placeholder={'fizzbuzz(5)\nfizzbuzz(15)'}
                  />
                  <p style={{ fontSize: 12, color: 'var(--muted)', margin: '6px 0 0' }}>
                    {callCount} call{callCount === 1 ? '' : 's'}.
                  </p>
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label htmlFor="pred-setup">Extra setup code (optional)</label>
                  <p style={{ fontSize: 12, color: 'var(--muted)', margin: '2px 0 6px' }}>
                    Only needed if the calls rely on something not in the question's code (helper defs, a fixture, an
                    import). Runs first; hidden from students.
                  </p>
                  <textarea
                    id="pred-setup"
                    className="form-control code"
                    rows={3}
                    value={prediction.setup || ''}
                    onChange={(e) => onChange({ ...prediction, setup: e.target.value })}
                  />
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
