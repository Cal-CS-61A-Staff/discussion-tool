import TestResultsPanel from './TestResultsPanel.jsx';
import { useTestRunner } from '../../hooks/useTestRunner.js';

export default function TestRunner({ groupId, worksheetId, source, code, question, disabled, label, lastSharedRun }) {
  const { results, running, error, run, pyLoading, cooling } = useTestRunner(groupId, worksheetId, source, question);

  // Only the browser that clicked "Run tests" populates local `results` —
  // for the shared editor, fall back to the group's last shared run so
  // teammates who didn't type still see the same pass/fail.
  const displayResults = results || lastSharedRun || null;
  const isSomeoneElsesRun = !results && Boolean(lastSharedRun);

  const canRun = !disabled && !running && !cooling && !pyLoading && Boolean(code && code.trim());
  const buttonText = pyLoading
    ? 'Loading Python…'
    : running
      ? 'Running…'
      : cooling
        ? 'Wait…'
        : label || 'Run tests';

  return (
    <div className="predict-row" style={{ marginTop: 14 }}>
      <button className="btn btn-primary run-btn" onClick={() => run(code)} disabled={!canRun}>
        {buttonText}
      </button>
      {error && (
        <div className="alert alert-danger" style={{ marginTop: 10, width: '100%' }}>
          {error}
        </div>
      )}
      <div style={{ width: '100%' }}>
        {isSomeoneElsesRun && (
          <p style={{ fontSize: 12, color: 'var(--muted)', margin: '10px 0 0' }}>
            Showing the most recent run, by {displayResults.by}.
          </p>
        )}
        <TestResultsPanel results={displayResults} />
      </div>
    </div>
  );
}
