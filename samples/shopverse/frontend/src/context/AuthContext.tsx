import { createContext, useState, ReactNode } from 'react';
import { login as apiLogin } from '../api/authApi';

interface AuthState { token: string | null; role: string | null; userId: number | null }
export const AuthContext = createContext<{ state: AuthState; login: (e: string, p: string) => Promise<void>; logout: () => void } | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ token: localStorage.getItem('token'), role: localStorage.getItem('role'), userId: Number(localStorage.getItem('uid')) || null });

  async function login(email: string, password: string) {
    const res = await apiLogin(email, password);
    localStorage.setItem('token', res.token);
    localStorage.setItem('role', res.role);
    setState({ token: res.token, role: res.role, userId: null });
  }

  function logout() {
    localStorage.clear();
    setState({ token: null, role: null, userId: null });
  }

  return <AuthContext.Provider value={{ state, login, logout }}>{children}</AuthContext.Provider>;
}
