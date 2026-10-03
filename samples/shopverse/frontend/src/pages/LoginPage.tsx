import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { forgotPassword } from '../api/authApi';

export default function LoginPage() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await login(email, password);
      nav('/');
    } catch {
      setError('Invalid email or password');
    }
  }

  return (
    <form onSubmit={submit}>
      <input value={email} onChange={e => setEmail(e.target.value)} placeholder="Email" />
      <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Password" />
      {error && <p className="error">{error}</p>}
      <button type="submit">Sign in</button>
      <button type="button" onClick={() => forgotPassword(email)}>Forgot password?</button>
    </form>
  );
}
