import { api } from './client.js';

export const createWorksheet = (sectionId, { title, description, due_date }) =>
  api.post(`/sections/${sectionId}/worksheets`, { title, description, due_date });
export const updateWorksheet = (worksheetId, { title, description, due_date, is_published }) =>
  api.put(`/worksheets/${worksheetId}`, { title, description, due_date, is_published });
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
