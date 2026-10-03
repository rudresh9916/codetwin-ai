import { useEffect, useState } from 'react';
import { getUser, updateProfile } from '../api/userApi';
import { useAuth } from '../hooks/useAuth';

export default function ProfilePage() {
  const { state } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  useEffect(() => { if (state.userId) getUser(state.userId).then(u => { setName(u.name); setEmail(u.email); }); }, [state.userId]);
  return (
    <form onSubmit={e => { e.preventDefault(); if (state.userId) updateProfile(state.userId, name, email); }}>
      <input value={name} onChange={e => setName(e.target.value)} />
      <input value={email} onChange={e => setEmail(e.target.value)} />
      <button>Save</button>
    </form>
  );
}
