import { useState } from 'react';

const GRADING_MODE_LABEL = { simple: 'simple', doctest: 'doctest', pltest: 'custom tests', discussion: 'discussion' };

export default function TaQuestionList({ questions }) {
  const [expandedId, setExpandedId] = useState(null);

  if (questions.length === 0) {
    return <p style={{ color: 'var(--muted)' }}>No questions yet — add one above.</p>;
  }

  return (
    <div className="list-group">
      {questions.map((q) => {
        const expanded = expandedId === q.id;
        return (
          <div key={q.id} className="list-group-item">
            <div
              style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
              onClick={() => setExpandedId(expanded ? null : q.id)}
            >
              <span>
                <b>{q.order_index + 1}.</b> {q.title}
                <span className="badge badge-default" style={{ marginLeft: 8 }}>
                  {GRADING_MODE_LABEL[q.grading_mode] || q.grading_mode}
                </span>
              </span>
              <span style={{ color: 'var(--muted)' }}>{expanded ? '▲' : '▼'}</span>
            </div>
            {expanded && (
              <div style={{ marginTop: 10 }}>
                <div className="q-label">Prompt</div>
                <p className="q-text">{q.prompt}</p>

                {q.starter_code && (
                  <>
                    <div className="q-label">Starter code</div>
                    <pre className="code-editor-wrap" style={{ padding: 10, color: '#eee', margin: '0 0 12px' }}>
                      <code className="code">{q.starter_code}</code>
                    </pre>
                  </>
                )}

                {q.expected_output && (
                  <div className="alert alert-info">
                    <strong>Expected output</strong>
                    <div className="rows">
                      <div className="code">{q.expected_output}</div>
                    </div>
                  </div>
                )}

                {q.test_cases && q.test_cases.length > 0 && (
                  <>
                    <div className="q-label">Test cases</div>
                    <div className="list-group" style={{ marginBottom: 12 }}>
                      {q.test_cases.map((c, i) => (
                        <div key={i} className="list-group-item">
                          <span className="code">{c.call}</span> → <span className="code">{c.expected}</span>
                        </div>
                      ))}
                    </div>
                  </>
                )}

                {q.grading_mode === 'pltest' && q.test_code && (
                  <>
                    <div className="q-label">Test code</div>
                    <pre className="code-editor-wrap" style={{ padding: 10, color: '#eee', margin: '0 0 12px' }}>
                      <code className="code">{q.test_code}</code>
                    </pre>
                  </>
                )}

                {q.reference_solution && (
                  <>
                    <div className="q-label">Reference solution</div>
                    <pre className="code-editor-wrap" style={{ padding: 10, color: '#eee', margin: '0 0 12px' }}>
                      <code className="code">{q.reference_solution}</code>
                    </pre>
                  </>
                )}

                {q.solution_markdown && (
                  <>
                    <div className="q-label">Solution</div>
                    <p className="q-text">{q.solution_markdown}</p>
                  </>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
