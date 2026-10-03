import client from './client';

export interface Product { id: number; name: string; description: string; price: number; category: string; imageUrl: string; rating: number }

export const listProducts = (category?: string) =>
  client.get<Product[]>('/products', { params: { category } }).then(r => r.data);

export const searchProducts = (q: string) => client.get<Product[]>('/products/search', { params: { q } }).then(r => r.data);

export const getProduct = (id: number) => client.get<Product>(`/products/${id}`).then(r => r.data);

export const getReviews = (productId: number) => client.get(`/reviews/product/${productId}`).then(r => r.data);
