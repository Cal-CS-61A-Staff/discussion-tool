import { api } from './client.js';

export const listClasses = () => api.get('/classes');
export const listSections = () => api.get('/sections');
export const myGroups = () => api.get('/me/groups');
export const sectionWorksheets = (sectionId) => api.get(`/sections/${sectionId}/worksheets`);
export const classWorksheets = (classId) => api.get(`/classes/${classId}/worksheets`);
export const sectionGroups = (sectionId) => api.get(`/sections/${sectionId}/groups`); // TA-only
export const sectionProgress = (sectionId) => api.get(`/sections/${sectionId}/progress`); // TA-only
export const joinableGroups = (sectionId) => api.get(`/sections/${sectionId}/groups/joinable`);
export const joinGroupByNumber = (sectionId, number) => api.post(`/sections/${sectionId}/groups/join`, { number });
export const workIndividually = (sectionId) => api.post(`/sections/${sectionId}/work-individually`);

// Class-level student roster (server/blueprints/sections.py) — any TA/co-teacher on the class, or an admin.
export const listClassStudents = (classId) => api.get(`/classes/${classId}/students`);
export const addClassStudent = (classId, email, name) =>
  api.post(`/classes/${classId}/students`, { email, ...(name ? { name } : {}) });
export const removeClassStudent = (classId, email) =>
  api.delete(`/classes/${classId}/students`, { email });

// TA-only group management (server/blueprints/admin.py)
export const createGroups = (sectionId, count) => api.post(`/sections/${sectionId}/groups`, { count });
export const renameGroup = (groupId, name) => api.put(`/groups/${groupId}`, { name });
export const deleteGroup = (groupId) => api.delete(`/groups/${groupId}`);
export const removeGroupMember = (groupId, userId) => api.delete(`/groups/${groupId}/members/${userId}`);

// Discussion-section management (server/blueprints/admin.py)
export const createSection = (classId, name) => api.post('/sections', { class_id: classId, name });
export const deleteSection = (sectionId) => api.delete(`/sections/${sectionId}`);
export const updateSectionDetails = (sectionId, name) => api.put(`/sections/${sectionId}/details`, { name });
export const listCoTeachers = (sectionId) => api.get(`/sections/${sectionId}/co-teachers`);
export const addCoTeacher = (sectionId, email) => api.post(`/sections/${sectionId}/co-teachers`, { email });
export const removeCoTeacher = (sectionId, userId) => api.delete(`/sections/${sectionId}/co-teachers/${userId}`);
