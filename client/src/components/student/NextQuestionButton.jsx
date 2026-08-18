export default function NextQuestionButton({ ready, allRated, hasPassingRun, ratedCount, memberCount, onAdvance }) {
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

  return (
    <div className="next-row">
      <span className="wait-note">{note}</span>
      <button className="btn btn-primary" onClick={onAdvance} disabled={!ready}>
        Next question →
      </button>
    </div>
  );
}
