import { Link } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useCart } from '../hooks/useCart';

export default function Navbar() {
  const { state, logout } = useAuth();
  const { items } = useCart();
  const count = Object.values(items).reduce((a, b) => a + b, 0);
  return (
    <nav className="nav">
      <Link to="/">ShopVerse</Link>
      <Link to="/cart">Cart ({count})</Link>
      {state.token ? <><Link to="/orders">Orders</Link><Link to="/profile">Profile</Link><button onClick={logout}>Logout</button></> : <Link to="/login">Login</Link>}
      {state.role === 'ADMIN' && <Link to="/admin">Admin</Link>}
    </nav>
  );
}
