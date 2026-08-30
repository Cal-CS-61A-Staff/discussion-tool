export const isStaff = (user) => user?.role === 'ta' || user?.role === 'admin';
