export default function TestResultsPanel({ results }) {
  if (!results) return null;

  if (results.error) {
    return (
      <div className="alert alert-danger" style={{ marginTop: 12 }}>
        <strong>Couldn&apos;t run your code</strong>
        <div className="rows">
          <div>{results.error}</div>
        </div>
      </div>
    );
  }

  const allPassed = results.total_count > 0 && results.passed_count === results.total_count;

  return (
    <div className={`alert ${allPassed ? 'alert-success' : 'alert-warning'}`} style={{ marginTop: 12 }}>
      <strong>{results.passed_count} of {results.total_count} test cases passed</strong>
      <div className="list-group" style={{ marginTop: 8 }}>
        {results.test_results.map((t, i) => (
          <div
            key={i}
            className="list-group-item"
            style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}
          >
            <span>
              <span className={`badge ${t.passed ? 'badge-success' : 'badge-danger'}`} style={{ marginRight: 8 }}>
                {t.passed ? '✓' : '✗'}
              </span>
              {t.name}
            </span>
            {!t.passed && t.message && <span style={{ color: 'var(--muted)', fontSize: 12 }}>{t.message}</span>}
          </div>
        ))}
      </div>
      {results.student_output && (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', marginBottom: 4 }}>
            Output
          </div>
          <pre className="code-editor-wrap" style={{ padding: 10, color: '#eee', margin: 0 }}>
            <code className="code">{results.student_output}</code>
          </pre>
        </div>
      )}
    </div>
  );
}
