const STATUS_LABEL = { on_pace: 'on pace', stuck: 'stuck', done: 'done' };
const STATUS_PANEL_CLASS = { on_pace: 'panel-success', stuck: 'panel-warning', done: 'panel-default' };

function ratingColor(value) {
  if (value === null || value === undefined) return '#ccc';
  if (value <= 2) return '#d9534f';
  if (value === 3) return '#f0ad4e';
  return '#5cb85c';
}

export default function GroupTile({ group, onClick }) {
  const pct =
    group.total_questions > 0 ? Math.round((group.current_question_index / group.total_questions) * 100) : 0;

  return (
    <div className={`panel panel-clickable ${STATUS_PANEL_CLASS[group.status] || ''}`} onClick={onClick}>
      <div className="panel-heading">
        <h4>{group.name}</h4>
        <span className="badge badge-default" style={{ background: 'rgba(255,255,255,0.3)', color: 'inherit' }}>
          {STATUS_LABEL[group.status] || group.status}
        </span>
      </div>
      <div className="panel-body">
        <div className="progress" style={{ marginBottom: 10 }}>
          <div
            className={`progress-bar ${group.status === 'stuck' ? 'progress-bar-warning' : 'progress-bar-success'}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="group-tile-typist-row">
          <span>Question</span>
          <b>
            {Math.min(group.current_question_index + 1, group.total_questions)} of {group.total_questions}
          </b>
        </div>
        <div className="group-tile-typist-row">
          <span>Typist</span>
          <b>{group.typist_name || '—'}</b>
        </div>
        <div className="group-tile-typist-row">
          <span>Avg rating</span>
          <b style={{ color: ratingColor(group.average_rating) }}>{group.average_rating ?? '—'}</b>
        </div>
        <div className="rating-dots">
          {group.members.map((m) => (
            <div key={m.user_id} className="d" style={{ background: ratingColor(m.rating) }} title={m.display_name}>
              {m.rating ?? '–'}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
