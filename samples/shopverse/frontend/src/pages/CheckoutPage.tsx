import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { placeOrder } from '../api/orderApi';
import { useCart } from '../hooks/useCart';
import { useAuth } from '../hooks/useAuth';
import { formatInr } from '../utils/format';

export default function CheckoutPage() {
  const { items, total, refresh } = useCart();
  const { state } = useAuth();
  const nav = useNavigate();
  const [address, setAddress] = useState('');
  const [coupon, setCoupon] = useState('');
  const [cardToken, setCardToken] = useState('tok_visa');
  const [status, setStatus] = useState('');

  async function pay() {
    if (!state.userId) return;
    const lines = Object.entries(items).map(([productId, quantity]) => ({ productId: Number(productId), quantity }));
    const order = await placeOrder(state.userId, lines, address, cardToken, coupon || undefined);
    if (order.status === 'PAYMENT_FAILED') {
      setStatus('Payment failed — please try another card.');
    } else {
      await refresh();
      nav('/orders');
    }
  }

  return (
    <main>
      <textarea value={address} onChange={e => setAddress(e.target.value)} placeholder="Shipping address" />
      <input value={coupon} onChange={e => setCoupon(e.target.value)} placeholder="Coupon" />
      <input value={cardToken} onChange={e => setCardToken(e.target.value)} placeholder="Card token" />
      <p>Payable: {formatInr(total)}</p>
      <button onClick={pay}>Pay now</button>
      {status && <p className="error">{status}</p>}
    </main>
  );
}
