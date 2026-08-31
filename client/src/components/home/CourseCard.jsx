export default function CourseCard({ course, onClick }) {
  return (
    <div className="panel panel-clickable course-card" onClick={onClick}>
      <div className="course-card-heading">
        <h4>{course.course_name}</h4>
      </div>
      <div className="panel-body" />
    </div>
  );
}
