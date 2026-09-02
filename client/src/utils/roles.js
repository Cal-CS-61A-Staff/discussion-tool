export const isAdmin = (user) => user?.role === 'admin';

// Staff standing is per class now. `isStaff` only answers "is this user
// staff-capable anywhere" (admins always; anyone who staffs ≥1 class) —
// for the nav. Page-level "is the current user staff of THIS class" uses
// classIsStaff with the class payload's `my_role`.
export const isStaff = (user) => user?.role === 'admin' || user?.staffs_any_class === true;

export const classIsStaff = (klass, user) => user?.role === 'admin' || klass?.my_role === 'staff';
