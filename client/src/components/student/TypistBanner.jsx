export default function TypistBanner({ members, isMeTypist, onPass, onClaim }) {
  const typist = members.find((m) => m.is_typist);
  const others = members.filter((m) => !m.is_me);

  return (
    <div className={`alert ${isMeTypist ? 'alert-success' : 'alert-warning'}`} style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
      <span>
        {isMeTypist ? (
          <>
            You are the <strong>typist</strong> for this question. Others can watch but not edit.
          </>
        ) : typist ? (
          <>
            <strong>{typist.display_name}</strong> is the typist for this question. You&apos;re in view-only mode.
          </>
        ) : (
          'No one is typing yet.'
        )}
      </span>
      {isMeTypist && others.length > 0 && (
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {others.map((m) => (
            <button key={m.user_id} className="btn btn-sm" onClick={() => onPass(m.user_id)}>
              Pass to {m.display_name}
            </button>
          ))}
        </div>
      )}
      {!typist && (
        <button className="btn btn-sm" style={{ marginLeft: 'auto' }} onClick={onClaim}>
          Claim the pen
        </button>
      )}
    </div>
  );
}
