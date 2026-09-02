import { api } from './client.js';

// The anonymous student entry point — a per-assignment share link
// (server/blueprints/w.py). No account, no class enrollment.
export const resolve = (code) => api.get(`/w/${code}`);
export const join = (code, { name, number }) => api.post(`/w/${code}/join`, { name, number });
export const workIndividually = (code, { name }) => api.post(`/w/${code}/work-individually`, { name });
export const exportHref = (code, groupId) => `/api/w/${code}/g/${groupId}/export`;
