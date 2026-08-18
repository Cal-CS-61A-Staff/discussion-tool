import { useState } from 'react';
import GraderFeedbackPanel from './GraderFeedbackPanel.jsx';
import TestResultsPanel from './TestResultsPanel.jsx';
import { useTestRunner } from '../../hooks/useTestRunner.js';

export default function TestRunner({
  groupId,
  worksheetId,
  source,
  code,
  predictCall,
  disabled,
  label,
  graderCooldown,
  lastSharedRun,
}) {
  const [prediction, setPrediction] = useState('');
  const { results, running, error, run, remainingSeconds, cooldownSeconds } = useTestRunner(
    groupId,
    worksheetId,
    source,
    graderCooldown
  );

  // Only the browser that clicked "Run tests" ever populates local
  // `results` — for the shared editor, fall back to the group's last
  // shared run (server-computed, same for everyone) so teammates who
  // didn't do the typing still see the same pass/fail confirmation.
  const displayResults = results || lastSharedRun || null;
  const isSomeoneElsesRun = !results && Boolean(lastSharedRun);

  const onCooldown = remainingSeconds > 0;
  const canRun = !disabled && !running && !onCooldown && Boolean(code && code.trim()) && Boolean(prediction.trim());
  const ringCircumference = 2 * Math.PI * 6.5;
  const ringOffset =
    cooldownSeconds > 0 ? ringCircumference * (1 - remainingSeconds / cooldownSeconds) : ringCircumference;
  const question = predictCall ? (
    <>
      What do you think <code className="code">{predictCall}</code> will output?
    </>
  ) : (
    'What do you think this code will output?'
  );

  return (
    <div className="predict-row" style={{ marginTop: 14 }}>
      <div className="predict-field form-group" style={{ marginBottom: 0 }}>
        <label htmlFor={`prediction-${source}`}>{question}</label>
        <textarea
          id={`prediction-${source}`}
          className="form-control code"
          rows={3}
          value={prediction}
          onChange={(e) => setPrediction(e.target.value)}
          placeholder="Type your prediction before running"
          disabled={disabled}
        />
      </div>
      <button className="btn btn-primary run-btn" onClick={() => run(code, prediction.trim())} disabled={!canRun}>
        {onCooldown && (
          <svg className="cooldown-ring" viewBox="0 0 16 16">
            <circle
              cx="8"
              cy="8"
              r="6.5"
              strokeDasharray={ringCircumference}
              strokeDashoffset={ringOffset}
            />
          </svg>
        )}
        {onCooldown ? `Wait ${remainingSeconds}s` : running ? 'Running…' : label || 'Run tests'}
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
        <GraderFeedbackPanel feedback={displayResults?.prediction_feedback} />
        <TestResultsPanel results={displayResults} />
      </div>
    </div>
  );
}
