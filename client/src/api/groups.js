import { api } from './client.js';

export const getGroupState = (groupId, worksheetId, signal) =>
  api.get(`/groups/${groupId}/state?worksheet_id=${worksheetId}`, { signal });
export const updateCode = (groupId, worksheetId, code) =>
  api.put(`/groups/${groupId}/code`, { worksheet_id: worksheetId, code });
export const updateScratchCode = (groupId, worksheetId, code) =>
  api.put(`/groups/${groupId}/scratch-code`, { worksheet_id: worksheetId, code });
export const giveUpTypist = (groupId, worksheetId) =>
  api.post(`/groups/${groupId}/typist/give-up`, { worksheet_id: worksheetId });
export const leaveGroup = (groupId, worksheetId) =>
  api.post(`/groups/${groupId}/leave`, { worksheet_id: worksheetId });
export const updateGroupName = (groupId, name) => api.put(`/groups/${groupId}/name`, { name });
export const submitRating = (groupId, worksheetId, value, questionId) =>
  api.post(`/groups/${groupId}/ratings`, {
    worksheet_id: worksheetId,
    value,
    ...(questionId != null ? { question_id: questionId } : {}),
  });
export const advanceGroup = (groupId, worksheetId) =>
  api.post(`/groups/${groupId}/advance`, { worksheet_id: worksheetId });
export const forceAdvanceGroup = (groupId, worksheetId) =>
  api.post(`/groups/${groupId}/advance/force`, { worksheet_id: worksheetId });
export const getGroupDetail = (groupId, worksheetId, signal) =>
  api.get(`/groups/${groupId}/detail?worksheet_id=${worksheetId}`, { signal });
export const releaseTypist = (groupId, worksheetId) =>
  api.post(`/groups/${groupId}/typist/release`, { worksheet_id: worksheetId });
// Grading runs in the browser (client/src/pyodide/); these just persist the
// result the client computed.
export const runTests = (groupId, worksheetId, code, results, source) =>
  api.post(`/groups/${groupId}/run-tests`, { worksheet_id: worksheetId, code, results, source });
export const getGroupHistory = (groupId) => api.get(`/groups/${groupId}/history`);
export const getGroupWork = (groupId, worksheetId) => api.get(`/groups/${groupId}/worksheets/${worksheetId}/work`);
export const practiceRun = (groupId, worksheetId, questionId, code, results) =>
  api.post(`/groups/${groupId}/worksheets/${worksheetId}/questions/${questionId}/practice-run`, { code, results });
export const submitResponse = (groupId, worksheetId, questionId, response, extra) =>
  api.post(`/groups/${groupId}/worksheets/${worksheetId}/questions/${questionId}/response`, { response, ...extra });
export const submitPrediction = (groupId, worksheetId, questionId, text) =>
  api.post(`/groups/${groupId}/worksheets/${worksheetId}/questions/${questionId}/prediction`, { text });
