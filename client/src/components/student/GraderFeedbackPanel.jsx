import { useEffect, useState } from 'react';

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
  const [dismissed, setDismissed] = useState(false);

  // Keyed on content, not object identity: `feedback` can be re-derived
  // from a fresh poll (e.g. a teammate's last shared run) with an
  // identical value but a new object reference every ~2.5s, which would
  // otherwise silently un-dismiss the panel on every poll.
  useEffect(() => {
    setDismissed(false);
  }, [feedback?.call, feedback?.expected, feedback?.got, feedback?.is_match]);

  if (!feedback || dismissed) return null;

  return (
    <div className="grader-feedback-panel">
      <div className="grader-feedback-header">
        <span>Grader Feedback</span>
        <button className="modal-close-btn" onClick={() => setDismissed(true)}>
          ✕
        </button>
      </div>
      <div className="grader-feedback-body">
        <p className="grader-feedback-title">{feedback.is_match ? 'Test passed:' : 'Test failed:'}</p>
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
      </div>
    </div>
  );
}
