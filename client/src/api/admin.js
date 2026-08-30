import { api } from './client.js';

export const createWorksheet = (classId, { title, description }) =>
  api.post(`/classes/${classId}/worksheets`, { title, description });
export const getWorksheet = (worksheetId) => api.get(`/worksheets/${worksheetId}`);
export const updateWorksheet = (worksheetId, { title, description, is_published }) =>
  api.put(`/worksheets/${worksheetId}`, { title, description, is_published });
export const deleteWorksheet = (worksheetId) => api.delete(`/worksheets/${worksheetId}`);
export const publishWorksheet = (worksheetId) => api.post(`/worksheets/${worksheetId}/publish`);
export const unpublishWorksheet = (worksheetId) => api.post(`/worksheets/${worksheetId}/unpublish`);

export const createQuestion = (worksheetId, payload) => api.post(`/worksheets/${worksheetId}/questions`, payload);
export const updateQuestion = (questionId, payload) => api.put(`/questions/${questionId}`, payload);
export const deleteQuestion = (questionId) => api.delete(`/questions/${questionId}`);
export const listQuestions = (worksheetId) => api.get(`/worksheets/${worksheetId}/questions`);
export const reorderQuestions = (worksheetId, order) =>
  api.put(`/worksheets/${worksheetId}/questions/reorder`, { order });
export const getGrades = (worksheetId) => api.get(`/worksheets/${worksheetId}/grades`);

export const listTas = () => api.get('/tas');
export const assignSectionTa = (sectionId, taUserId) => api.put(`/sections/${sectionId}/ta`, { ta_user_id: taUserId });
export const importRoster = (csv) => api.post('/roster/import', { csv });
export const importEnrollmentRoster = (csv) => api.post('/roster/import-enrollment', { csv });

export const createClass = (courseName) => api.post('/classes', { course_name: courseName });
export const deleteClass = (classId) => api.delete(`/classes/${classId}`);
