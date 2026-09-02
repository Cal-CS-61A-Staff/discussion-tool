import { api } from './client.js';

// Staff/admin only — students have no class list; they use a share link
// (client/src/api/w.js).
export const listClasses = () => api.get('/classes');
export const classWorksheets = (classId) => api.get(`/classes/${classId}/worksheets`);

// TA dashboard watch list (staff-only).
export const getWatchedNumbers = (classId) => api.get(`/classes/${classId}/watched-numbers`);
export const setWatchedNumbers = (classId, numbers) =>
  api.put(`/classes/${classId}/watched-numbers`, { numbers });

// Class staff roster (staff/admin).
export const listClassStaff = (classId) => api.get(`/classes/${classId}/staff`);
export const addClassStaff = (classId, email) => api.post(`/classes/${classId}/staff`, { email });
export const removeClassStaff = (classId, userId) => api.delete(`/classes/${classId}/staff/${userId}`);

// Rooms (was "sections") — admin-configured, staff-only.
export const listSections = () => api.get('/sections');
export const createSection = (classId, name) => api.post('/sections', { class_id: classId, name });
export const deleteSection = (sectionId) => api.delete(`/sections/${sectionId}`);
export const updateSectionDetails = (sectionId, name, assignedNumbers) =>
  api.put(`/sections/${sectionId}/details`, { name, ...(assignedNumbers !== undefined ? { assigned_numbers: assignedNumbers } : {}) });
export const listCoTeachers = (sectionId) => api.get(`/sections/${sectionId}/co-teachers`);
export const addCoTeacher = (sectionId, email) => api.post(`/sections/${sectionId}/co-teachers`, { email });
export const removeCoTeacher = (sectionId, userId) => api.delete(`/sections/${sectionId}/co-teachers/${userId}`);
