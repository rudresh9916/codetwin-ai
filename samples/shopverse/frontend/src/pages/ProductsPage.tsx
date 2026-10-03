import { useEffect, useState } from 'react';
import { listProducts, searchProducts, Product } from '../api/productApi';
import ProductCard from '../components/ProductCard';
import { useCart } from '../hooks/useCart';

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<string | undefined>();
  const { add } = useCart();

  useEffect(() => {
    if (query.length > 2) {
      searchProducts(query).then(setProducts);
    } else {
      listProducts(category).then(setProducts);
    }
  }, [query, category]);

  return (
    <main>
      <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search products" />
      <select onChange={e => setCategory(e.target.value || undefined)}>
        <option value="">All</option><option>Electronics</option><option>Fashion</option><option>Home</option>
      </select>
      <div className="grid">{products.map(p => <ProductCard key={p.id} product={p} onAdd={id => add(id)} />)}</div>
    </main>
  );
}
