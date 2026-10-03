import client from './client';

export const getCart = (userId: number) => client.get(`/cart/${userId}`).then(r => r.data);
export const addToCart = (userId: number, productId: number, qty: number) =>
  client.post(`/cart/${userId}/items`, null, { params: { productId, qty } });
export const removeFromCart = (userId: number, productId: number) => client.delete(`/cart/${userId}/items/${productId}`);
export const getCartTotal = (userId: number) => client.get(`/cart/${userId}/total`).then(r => r.data);
