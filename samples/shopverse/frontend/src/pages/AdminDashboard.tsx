import { useEffect, useState } from 'react';
import { getAdminDashboard } from '../api/userApi';
import { formatInr } from '../utils/format';

export default function AdminDashboard() {
  const [data, setData] = useState<any>(null);
  useEffect(() => { getAdminDashboard().then(setData); }, []);
  if (!data) return <p>Loading…</p>;
  return (
    <section>
      <h2>Admin</h2>
      <p>Active users: {data.activeUsers}</p>
      <p>Revenue: {formatInr(data.revenue)}</p>
      <p>Pending orders: {data.pendingOrders}</p>
    </section>
  );
}
