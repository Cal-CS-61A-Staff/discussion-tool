export default function CourseCard({ course, onClick }) {
  return (
    <div className="panel panel-clickable course-card" onClick={onClick}>
      <div className="course-card-heading">
        <h4>{course.course_name}</h4>
      </div>
      <div className="panel-body">
        <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)' }}>Click to view assignments →</p>
      </div>
    </div>
  );
}
