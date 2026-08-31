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

  // A real error (the call itself raised, or the code didn't even load) is
  // shown outright — that's a bug worth surfacing, not a "prediction" to
  // grade. A plain value mismatch instead hides the actual answer, so
  // getting it wrong doesn't just hand the student the answer — they're
  // expected to trace through their own code to find it.
  if (feedback.is_error) {
    return (
      <div className="grader-feedback-panel grader-feedback-panel--fail">
        <div className="grader-feedback-header">
          <span>Grader Feedback</span>
        </div>
        <div className="grader-feedback-body">
          <p className="grader-feedback-title">
            <span className="badge badge-danger" style={{ marginRight: 8 }}>
              !
            </span>
            Your code raised an error on this call:
          </p>
          <pre className="grader-feedback-call">
            <code>{withNumberHighlights(feedback.call)}</code>
          </pre>
          <pre className="grader-feedback-values" style={{ whiteSpace: 'pre-wrap' }}>
            {feedback.traceback}
          </pre>
        </div>
      </div>
    );
  }

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
          {feedback.is_match ? 'Prediction correct:' : 'Prediction incorrect'}
        </p>
        <pre className="grader-feedback-call">
          <code>{withNumberHighlights(feedback.call)}</code>
        </pre>
        {feedback.is_match ? (
          <>
            <div className="grader-feedback-section">
              <span className="grader-feedback-label">Expected:</span>
              <pre className="grader-feedback-values">{feedback.expected}</pre>
            </div>
            <div className="grader-feedback-section">
              <span className="grader-feedback-label">Got:</span>
              <pre className="grader-feedback-values">{feedback.got}</pre>
            </div>
          </>
        ) : (
          <p className="grader-feedback-note">
            Not quite. Trace through the code line by line and try again — separate from whether your tests pass
            below.
          </p>
        )}
      </div>
    </div>
  );
}
