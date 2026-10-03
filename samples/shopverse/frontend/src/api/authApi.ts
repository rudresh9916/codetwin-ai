import client from './client';

export interface AuthResponse { token: string; role: string }

export const login = (email: string, password: string) =>
  client.post<AuthResponse>('/auth/login', { email, password }).then(r => r.data);

export const register = (name: string, email: string, password: string) =>
  client.post<AuthResponse>('/auth/register', { name, email, password }).then(r => r.data);

export const forgotPassword = (email: string) => client.post(`/auth/forgot-password?email=${email}`);
