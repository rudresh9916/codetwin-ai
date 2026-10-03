import { Navigate } from 'react-router-dom';
import { ReactNode } from 'react';
import { useAuth } from '../hooks/useAuth';

export default function ProtectedRoute({ children, admin }: { children: ReactNode; admin?: boolean }) {
  const { state } = useAuth();
  if (!state.token) return <Navigate to="/login" />;
  if (admin && state.role !== 'ADMIN') return <Navigate to="/" />;
  return <>{children}</>;
}
