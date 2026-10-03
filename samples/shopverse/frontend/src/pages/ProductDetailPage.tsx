import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { getProduct, getReviews, Product } from '../api/productApi';
import { useCart } from '../hooks/useCart';
import { formatInr } from '../utils/format';

export default function ProductDetailPage() {
  const { id } = useParams();
  const [product, setProduct] = useState<Product | null>(null);
  const [reviews, setReviews] = useState<any[]>([]);
  const { add } = useCart();

  useEffect(() => {
    getProduct(Number(id)).then(setProduct);
    getReviews(Number(id)).then(setReviews);
  }, [id]);

  if (!product) return <p>Loading…</p>;
  return (
    <article>
      <h1>{product.name}</h1>
      <div dangerouslySetInnerHTML={{ __html: product.description }} />
      <strong>{formatInr(product.price)}</strong>
      <button onClick={() => add(product.id)}>Add to cart</button>
      <ul>{reviews.map((r, i) => <li key={i}>{r.stars}★ {r.comment}</li>)}</ul>
    </article>
  );
}
