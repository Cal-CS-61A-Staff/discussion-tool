const LABELS = { 1: 'lost', 2: 'shaky', 3: 'okay', 4: 'solid', 5: 'got it' };

export default function ConfidenceScale({ value, onRate }) {
  return (
    <div className="confidence-scale">
      {[1, 2, 3, 4, 5].map((v) => (
        <div
          key={v}
          className={`confidence-btn ${value === v ? 'selected' : ''}`}
          data-v={v}
          onClick={() => onRate(v)}
        >
          {v}
          <span className="lab">{LABELS[v]}</span>
        </div>
      ))}
    </div>
  );
}
