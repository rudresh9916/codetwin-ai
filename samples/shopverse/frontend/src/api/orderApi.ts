import client from './client';

export interface OrderLine { productId: number; quantity: number }

export const placeOrder = (customerId: number, items: OrderLine[], shippingAddress: string, paymentMethodToken: string, couponCode?: string) =>
  client.post('/orders', { customerId, items, shippingAddress, paymentMethodToken, couponCode }).then(r => r.data);

export const getOrderHistory = (customerId: number) => client.get(`/orders/customer/${customerId}`).then(r => r.data);

export const cancelOrder = (orderId: number) => client.post(`/orders/${orderId}/cancel`).then(r => r.data);
