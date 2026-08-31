export const isStaff = (user) => user?.role === 'ta' || user?.role === 'admin';
export const isAdmin = (user) => user?.role === 'admin';
