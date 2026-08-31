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
export const submitAttempt = (groupId, worksheetId, prediction) =>
  api.post(`/groups/${groupId}/attempts`, { worksheet_id: worksheetId, prediction });
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
export const runTests = (groupId, worksheetId, code, prediction, source) =>
  api.post(`/groups/${groupId}/run-tests`, { worksheet_id: worksheetId, code, prediction, source });
export const getTestRunResult = (groupId, testRunId) => api.get(`/groups/${groupId}/run-tests/${testRunId}`);
export const getGroupHistory = (groupId) => api.get(`/groups/${groupId}/history`);
export const getGroupWork = (groupId, worksheetId) => api.get(`/groups/${groupId}/worksheets/${worksheetId}/work`);
export const practiceRun = (groupId, worksheetId, questionId, code, prediction) =>
  api.post(`/groups/${groupId}/worksheets/${worksheetId}/questions/${questionId}/practice-run`, { code, prediction });
export const submitResponse = (groupId, worksheetId, questionId, response) =>
  api.post(`/groups/${groupId}/worksheets/${worksheetId}/questions/${questionId}/response`, { response });
export const submitPrediction = (groupId, worksheetId, questionId, text) =>
  api.post(`/groups/${groupId}/worksheets/${worksheetId}/questions/${questionId}/prediction`, { text });
