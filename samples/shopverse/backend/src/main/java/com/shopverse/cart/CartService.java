package com.shopverse.cart;

import com.shopverse.product.Product;
import com.shopverse.product.ProductService;
import com.shopverse.inventory.InventoryService;
import org.springframework.stereotype.Service;
import java.math.BigDecimal;
import java.util.*;

/**
 * In-memory shopping carts keyed by user id.
 */
@Service
public class CartService {

    private final Map<Long, Map<Long, Integer>> carts = new HashMap<>();
    private final ProductService productService;
    private final InventoryService inventoryService;

    public CartService(ProductService productService, InventoryService inventoryService) {
        this.productService = productService;
        this.inventoryService = inventoryService;
    }

    public Map<Long, Integer> getCart(Long userId) {
        return carts.computeIfAbsent(userId, k -> new HashMap<>());
    }

    public void addItem(Long userId, Long productId, int qty) {
        if (inventoryService.getAvailable(productId) < qty) {
            throw new IllegalStateException("Not enough stock");
        }
        getCart(userId).merge(productId, qty, Integer::sum);
    }

    public void removeItem(Long userId, Long productId) {
        getCart(userId).remove(productId);
    }

    public BigDecimal total(Long userId) {
        BigDecimal total = BigDecimal.ZERO;
        for (Map.Entry<Long, Integer> e : getCart(userId).entrySet()) {
            total = total.add(productService.priceFor(e.getKey(), e.getValue()));
        }
        return total;
    }

    public void clear(Long userId) {
        carts.remove(userId);
    }
}
