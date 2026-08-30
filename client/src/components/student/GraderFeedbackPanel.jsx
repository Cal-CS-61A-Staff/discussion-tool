function withNumberHighlights(call) {
  return call.split(/(\d+)/g).map((part, i) =>
    /^\d+$/.test(part) ? (
      <span key={i} style={{ color: 'var(--brand)' }}>
        {part}
      </span>
    ) : (
      <span key={i}>{part}</span>
    )
  );
}

export default function GraderFeedbackPanel({ feedback }) {
  if (!feedback) return null;

  return (
    <div className={`grader-feedback-panel ${feedback.is_match ? 'grader-feedback-panel--pass' : 'grader-feedback-panel--fail'}`}>
      <div className="grader-feedback-header">
        <span>Grader Feedback</span>
      </div>
      <div className="grader-feedback-body">
        <p className="grader-feedback-title">
          <span className={`badge ${feedback.is_match ? 'badge-success' : 'badge-danger'}`} style={{ marginRight: 8 }}>
            {feedback.is_match ? '✓' : '✗'}
          </span>
          {feedback.is_match ? 'Prediction correct:' : 'Prediction incorrect:'}
        </p>
        <pre className="grader-feedback-call">
          <code>{withNumberHighlights(feedback.call)}</code>
        </pre>
        <div className="grader-feedback-section">
          <span className="grader-feedback-label">Expected:</span>
          <pre className="grader-feedback-values">{feedback.expected}</pre>
        </div>
        <div className="grader-feedback-section">
          <span className="grader-feedback-label">Got:</span>
          <pre className="grader-feedback-values">{feedback.got}</pre>
        </div>
        {!feedback.is_match && (
          <p className="grader-feedback-note">
            This checks your understanding of the code, separately from the test results below — your code can
            still pass every test case even if your prediction was off.
          </p>
        )}
      </div>
    </div>
  );
}
