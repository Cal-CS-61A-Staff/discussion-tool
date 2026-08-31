/** A dropdown of the classes the current user has privileges over — used
 * anywhere a staff action (creating an assignment, managing a class's
 * sections/groups, assigning a TA) needs an explicit "which class" choice,
 * since one person can be TA/admin on more than one course.
 */
export default function ClassFilterSelect({ classes, value, onChange, includeAllOption = true, id }) {
  return (
    <select
      id={id}
      className="form-control"
      style={{ maxWidth: 280 }}
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
    >
      {includeAllOption && <option value="">All classes</option>}
      {classes.map((c) => (
        <option key={c.id} value={c.id}>
          {c.course_name}
        </option>
      ))}
    </select>
  );
}
