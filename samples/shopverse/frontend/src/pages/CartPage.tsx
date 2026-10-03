import { Link } from 'react-router-dom';
import { useCart } from '../hooks/useCart';
import CartItem from '../components/CartItem';
import { formatInr } from '../utils/format';

export default function CartPage() {
  const { items, total, remove } = useCart();
  return (
    <main>
      <ul>{Object.entries(items).map(([pid, qty]) => <CartItem key={pid} name={`Product ${pid}`} qty={qty} price={0} onRemove={() => remove(Number(pid))} />)}</ul>
      <p>Total: {formatInr(total)}</p>
      <Link to="/checkout">Checkout</Link>
    </main>
  );
}
