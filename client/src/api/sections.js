import { api } from './client.js';

export const listSections = () => api.get('/sections');
export const myGroups = () => api.get('/me/groups');
export const sectionWorksheets = (sectionId) => api.get(`/sections/${sectionId}/worksheets`);
export const sectionGroups = (sectionId) => api.get(`/sections/${sectionId}/groups`); // TA-only
export const joinGroupByNumber = (sectionId, number) => api.post(`/sections/${sectionId}/groups/join`, { number });
export const workIndividually = (sectionId) => api.post(`/sections/${sectionId}/work-individually`);

// TA-only group management (server/blueprints/admin.py)
export const createGroups = (sectionId, count) => api.post(`/sections/${sectionId}/groups`, { count });
export const renameGroup = (groupId, name) => api.put(`/groups/${groupId}`, { name });
export const deleteGroup = (groupId) => api.delete(`/groups/${groupId}`);
