export default function CourseCard({ course, onClick, isAdmin, onToggleArchive, archiving }) {
  return (
    <div className="panel panel-clickable course-card" onClick={onClick}>
      <div className="course-card-heading">
        <h4>{course.course_name}</h4>
        {isAdmin && (
          <button
            type="button"
            className="course-card-archive-link"
            onClick={(e) => {
              e.stopPropagation();
              onToggleArchive();
            }}
            disabled={archiving}
          >
            {archiving ? '…' : course.is_archived ? 'Restore' : 'Archive'}
          </button>
        )}
      </div>
    </div>
  );
}
