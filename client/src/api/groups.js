import { api } from './client.js';

export const getGroupState = (groupId, worksheetId, signal) =>
  api.get(`/groups/${groupId}/state?worksheet_id=${worksheetId}`, { signal });
export const updateCode = (groupId, worksheetId, code) =>
  api.put(`/groups/${groupId}/code`, { worksheet_id: worksheetId, code });
export const claimTypist = (groupId, worksheetId) =>
  api.post(`/groups/${groupId}/typist/claim`, { worksheet_id: worksheetId });
export const passTypist = (groupId, worksheetId, toUserId) =>
  api.post(`/groups/${groupId}/typist/pass`, { worksheet_id: worksheetId, to_user_id: toUserId });
export const submitAttempt = (groupId, worksheetId, prediction) =>
  api.post(`/groups/${groupId}/attempts`, { worksheet_id: worksheetId, prediction });
export const submitRating = (groupId, worksheetId, value) =>
  api.post(`/groups/${groupId}/ratings`, { worksheet_id: worksheetId, value });
export const advanceGroup = (groupId, worksheetId) =>
  api.post(`/groups/${groupId}/advance`, { worksheet_id: worksheetId });
export const goBack = (groupId, worksheetId) =>
  api.post(`/groups/${groupId}/go-back`, { worksheet_id: worksheetId });
export const getGroupDetail = (groupId, worksheetId, signal) =>
  api.get(`/groups/${groupId}/detail?worksheet_id=${worksheetId}`, { signal });
export const releaseTypist = (groupId, worksheetId) =>
  api.post(`/groups/${groupId}/typist/release`, { worksheet_id: worksheetId });
export const runTests = (groupId, worksheetId, code, prediction, source) =>
  api.post(`/groups/${groupId}/run-tests`, { worksheet_id: worksheetId, code, prediction, source });
