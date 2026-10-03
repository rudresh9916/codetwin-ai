import { formatInr } from '../utils/format';

export default function CartItem({ name, qty, price, onRemove }: { name: string; qty: number; price: number; onRemove: () => void }) {
  return (
    <li className="cart-item">
      <span>{name} × {qty}</span>
      <span>{formatInr(price * qty)}</span>
      <button onClick={onRemove}>Remove</button>
    </li>
  );
}
