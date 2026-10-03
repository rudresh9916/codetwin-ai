package com.shopverse.order;

import org.springframework.web.bind.annotation.*;
import java.util.List;

/**
 * Checkout and order history endpoints.
 */
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public Order placeOrder(@RequestBody OrderRequest request) {
        return orderService.placeOrder(request);
    }

    @GetMapping("/{id}")
    public Order get(@PathVariable Long id) {
        return orderService.getById(id);
    }

    @GetMapping("/customer/{customerId}")
    public List<Order> history(@PathVariable Long customerId) {
        return orderService.history(customerId);
    }

    @PostMapping("/{id}/cancel")
    public Order cancel(@PathVariable Long id) {
        return orderService.cancelOrder(id);
    }

    @PostMapping("/{id}/ship")
    public Order ship(@PathVariable Long id, @RequestParam String tracking) {
        return orderService.ship(id, tracking);
    }
}
