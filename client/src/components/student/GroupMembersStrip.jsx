export default function GroupMembersStrip({ members }) {
  return (
    <div className="group-mini">
      {members.map((m) => (
        <div key={m.user_id} className={`mini-pill ${m.has_rated_current ? 'done' : ''}`}>
          <span className="dot" />
          {m.is_me ? 'you' : m.display_name}
        </div>
      ))}
    </div>
  );
}
