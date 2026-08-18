import { api } from './client.js';

export const login = (displayName, role) => api.post('/auth/login', { display_name: displayName, role });
export const me = () => api.get('/auth/me');
export const logout = () => api.post('/auth/logout');
