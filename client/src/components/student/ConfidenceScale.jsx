const LABELS = { 1: 'lost', 2: 'shaky', 3: 'okay', 4: 'solid', 5: 'got it' };

export default function ConfidenceScale({ value, onRate, submitting }) {
  return (
    <div className="confidence-scale">
      {[1, 2, 3, 4, 5].map((v) => (
        <button
          key={v}
          type="button"
          className={`confidence-btn ${value === v ? 'selected' : ''}`}
          data-v={v}
          onClick={() => onRate(v)}
          disabled={submitting}
        >
          {v}
          <span className="lab">{LABELS[v]}</span>
        </button>
      ))}
      {submitting && (
        <span style={{ fontSize: 11, color: 'var(--muted)', alignSelf: 'center', marginLeft: 4 }}>Saving…</span>
      )}
    </div>
  );
}
