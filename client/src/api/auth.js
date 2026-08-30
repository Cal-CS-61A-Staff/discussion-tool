import { api } from './client.js';

export const login = (displayName, role, email) => api.post('/auth/login', { display_name: displayName, role, email });
export const adminLogin = (adminId) => api.post('/auth/admin-login', { admin_id: adminId });
export const me = () => api.get('/auth/me');
export const logout = () => api.post('/auth/logout');
export const getAuthConfig = () => api.get('/auth/config');
