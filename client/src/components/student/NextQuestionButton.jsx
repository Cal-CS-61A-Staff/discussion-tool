export default function NextQuestionButton({
  ready,
  allRated,
  hasPassingRun,
  ratedCount,
  memberCount,
  onAdvance,
  onForceAdvance,
  isIndividual,
  advancing,
}) {
  let note;
  if (ready) {
    note = 'Everyone has rated and the group has a passing run — ready to advance.';
  } else if (!allRated && !hasPassingRun) {
    note = `Waiting on ${memberCount - ratedCount} of ${memberCount} group members to rate, and a passing "Run tests" with a correct prediction…`;
  } else if (!allRated) {
    note = `Waiting on ${memberCount - ratedCount} of ${memberCount} group members to rate…`;
  } else {
    note = 'Waiting on a passing "Run tests" (all test cases + correct prediction) before you can advance…';
  }

  const handleForceAdvance = () => {
    if (
      window.confirm(
        'Skip ahead anyway? This moves your whole group to the next question even though not everyone has rated and/or the tests haven\'t passed yet — use this if someone in your group can\'t come back (crashed tab, connection issue, etc).'
      )
    ) {
      onForceAdvance();
    }
  };

  return (
    <div>
      <div className="next-row">
        <span className="wait-note">{note}</span>
        <button className="btn btn-primary" onClick={onAdvance} disabled={!ready || advancing}>
          {advancing ? 'Advancing…' : 'Next question →'}
        </button>
      </div>
      {!ready && !isIndividual && (
        <p style={{ marginTop: 6 }}>
          <a
            href="/"
            style={{ fontSize: 12, color: 'var(--muted)' }}
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
