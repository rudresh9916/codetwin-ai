import { useEffect, useState } from 'react';
import { getCart, addToCart, removeFromCart, getCartTotal } from '../api/cartApi';
import { useAuth } from './useAuth';

export function useCart() {
  const { state } = useAuth();
  const [items, setItems] = useState<Record<string, number>>({});
  const [total, setTotal] = useState(0);

  async function refresh() {
    if (!state.userId) return;
    setItems(await getCart(state.userId));
    setTotal(await getCartTotal(state.userId));
  }

  useEffect(() => { refresh(); }, [state.userId]);

  return {
    items, total, refresh,
    add: async (productId: number, qty = 1) => { if (state.userId) { await addToCart(state.userId, productId, qty); await refresh(); } },
    remove: async (productId: number) => { if (state.userId) { await removeFromCart(state.userId, productId); await refresh(); } },
  };
}
