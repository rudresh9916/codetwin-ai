import client from './client';

export const getUser = (id: number) => client.get(`/users/${id}`).then(r => r.data);
export const updateProfile = (id: number, name: string, email: string) => client.put(`/users/${id}`, { name, email }).then(r => r.data);
export const getAdminDashboard = () => client.get('/admin/dashboard').then(r => r.data);
