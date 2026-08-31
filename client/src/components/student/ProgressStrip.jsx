/** `current`/`total` drive the "Question X of Y" label — always which one
 * you're looking at. The percent bar defaults to that same current/total
 * (the live worksheet page's `current` really is "how many are done," since
 * it's the group's actual position), but `completed` overrides just the bar
 * when the two need to differ — e.g. WorkBrowserPage's `current` is a
 * browse position, not a completion count, so "0 of 1" there shouldn't
 * read as "0% done" when that one question was already passed.
 */
export default function ProgressStrip({ current, total, completed }) {
  const pct = total > 0 ? Math.round(((completed ?? current) / total) * 100) : 0;
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--muted)', marginBottom: 6 }}>
        <span>
          Question {current + 1} of {total}
        </span>
        <span>{pct}% complete</span>
      </div>
      <div className="progress">
        <div className="progress-bar" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
