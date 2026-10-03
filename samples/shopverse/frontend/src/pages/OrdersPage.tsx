import { useEffect, useState } from 'react';
import { getOrderHistory, cancelOrder } from '../api/orderApi';
import { useAuth } from '../hooks/useAuth';
import { formatInr } from '../utils/format';

export default function OrdersPage() {
  const { state } = useAuth();
  const [orders, setOrders] = useState<any[]>([]);
  useEffect(() => { if (state.userId) getOrderHistory(state.userId).then(setOrders); }, [state.userId]);
  return (
    <ul>
      {orders.map(o => (
        <li key={o.id}>#{o.id} — {o.status} — {formatInr(o.total)}
          {o.status !== 'SHIPPED' && <button onClick={() => cancelOrder(o.id)}>Cancel</button>}
        </li>
      ))}
    </ul>
  );
}
