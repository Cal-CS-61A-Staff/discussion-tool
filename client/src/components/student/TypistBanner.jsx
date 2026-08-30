export default function TypistBanner({ members, isMeTypist, onGiveUp, givingUp }) {
  const typist = members.find((m) => m.is_typist);
  const me = members.find((m) => m.is_me);
  // Display names are self-chosen and not unique — someone logging in fresh
  // (a new tab, no matching email) can end up as a *different* account that
  // happens to share your name. Flag that explicitly rather than showing
  // your own name back at you as "the typist" with no explanation of why
  // you still can't type.
  const sameNameDifferentAccount = typist && me && !isMeTypist && typist.display_name === me.display_name;

  return (
    <div
      className={`alert ${isMeTypist ? 'alert-success' : 'alert-warning'}`}
      style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}
    >
      <span>
        {isMeTypist ? (
          <>
            You are the <strong>typist</strong> for this question. Others can watch but not edit.
          </>
        ) : typist ? (
          <>
            <strong>{typist.display_name}</strong>
            {sameNameDifferentAccount && ' (a different account with the same name as you)'} is the typist for this
            question. You&apos;re in view-only mode.
          </>
        ) : (
          'Assigning a typist…'
        )}
      </span>
      {isMeTypist && (
        <button className="btn btn-sm" style={{ marginLeft: 'auto' }} onClick={onGiveUp} disabled={givingUp}>
          {givingUp ? 'Giving up…' : 'Give up the pen'}
        </button>
      )}
    </div>
  );
}
