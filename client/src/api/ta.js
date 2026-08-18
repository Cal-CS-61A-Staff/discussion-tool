import { api } from './client.js';

export const getDashboard = (worksheetId, signal) => api.get(`/worksheets/${worksheetId}/dashboard`, { signal });
