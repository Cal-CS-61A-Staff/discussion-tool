export default function SectionCard({ section, onClick }) {
  return (
    <div className="panel panel-clickable" onClick={onClick}>
      <div className="panel-heading">
        <h4>{section.name}</h4>
        <span className="badge badge-default">{section.course_name}</span>
      </div>
      <div className="panel-body">
        <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)' }}>
          {section.worksheet_count} assignment{section.worksheet_count === 1 ? '' : 's'}
        </p>
      </div>
    </div>
  );
}
