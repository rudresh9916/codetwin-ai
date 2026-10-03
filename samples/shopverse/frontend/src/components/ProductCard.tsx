import { Link } from 'react-router-dom';
import { Product } from '../api/productApi';
import { formatInr, stars } from '../utils/format';

export default function ProductCard({ product, onAdd }: { product: Product; onAdd: (id: number) => void }) {
  return (
    <div className="card">
      <img src={product.imageUrl} alt={product.name} />
      <Link to={`/products/${product.id}`}>{product.name}</Link>
      <span>{stars(product.rating)}</span>
      <strong>{formatInr(product.price)}</strong>
      <button onClick={() => onAdd(product.id)}>Add to cart</button>
    </div>
  );
}
