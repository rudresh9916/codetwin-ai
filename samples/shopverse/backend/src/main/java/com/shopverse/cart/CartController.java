package com.shopverse.cart;

import org.springframework.web.bind.annotation.*;
import java.math.BigDecimal;
import java.util.Map;

@RestController
@RequestMapping("/api/cart")
public class CartController {

    private final CartService cartService;

    public CartController(CartService cartService) {
        this.cartService = cartService;
    }

    @GetMapping("/{userId}")
    public Map<Long, Integer> get(@PathVariable Long userId) {
        return cartService.getCart(userId);
    }

    @PostMapping("/{userId}/items")
    public void add(@PathVariable Long userId, @RequestParam Long productId, @RequestParam int qty) {
        cartService.addItem(userId, productId, qty);
    }

    @DeleteMapping("/{userId}/items/{productId}")
    public void remove(@PathVariable Long userId, @PathVariable Long productId) {
        cartService.removeItem(userId, productId);
    }

    @GetMapping("/{userId}/total")
    public BigDecimal total(@PathVariable Long userId) {
        return cartService.total(userId);
    }
}
