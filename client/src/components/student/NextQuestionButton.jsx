export default function NextQuestionButton({
  ready,
  allRated,
  hasPassingRun,
  predictionReady = true,
  ratedCount,
  memberCount,
  onAdvance,
  onForceAdvance,
  advancing,
}) {
  let note;
  if (ready) {
    note = 'Everyone has rated and the group has finished this question — ready to advance.';
  } else if (!allRated) {
    note = `Waiting on ${memberCount - ratedCount} of ${memberCount} group members to rate…`;
  } else if (!hasPassingRun) {
    note = 'Waiting on the group to finish this question…';
  } else if (!predictionReady) {
    note = 'Make your group’s prediction to continue…';
  } else {
    note = 'Almost there…';
  }

  const handleForceAdvance = () => {
    if (
      window.confirm(
        "Skip ahead anyway? This moves your whole group to the next question even though not everyone has rated yet — use this if someone in your group can't come back (crashed tab, connection issue, etc)."
      )
    ) {
      onForceAdvance();
    }
  };

  // Skipping only ever waives the ratings requirement, never the tests
  // (server/services/advance.py:try_advance enforces that regardless of
  // `force`) — so there's nothing to skip to if the tests haven't passed.
  // And with only one person in the group, there's no "someone else" who
  // could be the one stuck; they'd just rate and pass normally.
  const canSkip = !allRated && hasPassingRun && memberCount > 1;

  return (
    <div>
      <div className="next-row">
        <span className="wait-note">{note}</span>
        <button className="btn btn-primary" onClick={onAdvance} disabled={!ready || advancing}>
          {advancing ? 'Advancing…' : 'Next question →'}
        </button>
      </div>
      {canSkip && (
        <p style={{ marginTop: 8 }}>
          <a
            href="/"
            style={{ fontSize: 13, color: 'var(--brand)', fontWeight: 600, textDecoration: 'underline' }}
            onClick={(e) => {
              e.preventDefault();
              if (!advancing) handleForceAdvance();
            }}
          >
            {advancing ? 'Advancing…' : "Someone stuck and can't come back? Skip to the next question anyway"}
          </a>
        </p>
      )}
    </div>
  );
}
