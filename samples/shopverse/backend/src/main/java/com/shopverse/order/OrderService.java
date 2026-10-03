package com.shopverse.order;

import com.shopverse.inventory.InventoryService;
import com.shopverse.inventory.InventoryRepository;
import com.shopverse.inventory.InventoryItem;
import com.shopverse.notification.EmailService;
import com.shopverse.payment.PaymentService;
import com.shopverse.payment.Payment;
import com.shopverse.product.Product;
import com.shopverse.product.ProductService;
import com.shopverse.user.User;
import com.shopverse.user.UserService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final ProductService productService;
    private final UserService userService;
    private final PaymentService paymentService;
    private final InventoryService inventoryService;
    private final InventoryRepository inventoryRepository;
    private final EmailService emailService;

    public OrderService(OrderRepository orderRepository, ProductService productService, UserService userService,
                        PaymentService paymentService, InventoryService inventoryService,
                        InventoryRepository inventoryRepository, EmailService emailService) {
        this.orderRepository = orderRepository;
        this.productService = productService;
        this.userService = userService;
        this.paymentService = paymentService;
        this.inventoryService = inventoryService;
        this.inventoryRepository = inventoryRepository;
        this.emailService = emailService;
    }

    @Transactional
    public Order placeOrder(OrderRequest request) {
        User customer = userService.getById(request.customerId);
        if (!customer.isActive()) {
            throw new IllegalStateException("Inactive customer");
        }
        if (request.items == null || request.items.isEmpty()) {
            throw new IllegalArgumentException("Order must contain items");
        }
        Order order = new Order();
        order.setCustomer(customer);
        order.setShippingAddress(request.shippingAddress);
        BigDecimal total = BigDecimal.ZERO;
        for (OrderRequest.Line line : request.items) {
            Product product = productService.getById(line.productId);
            int available = inventoryService.getAvailable(product.getId());
            if (available < line.quantity) {
                throw new IllegalStateException("Insufficient stock for " + product.getName());
            }
            OrderItem item = new OrderItem();
            item.setProduct(product);
            item.setQuantity(line.quantity);
            item.setUnitPrice(product.getPrice());
            item.setOrder(order);
            order.getItems().add(item);
            total = total.add(productService.priceFor(product.getId(), line.quantity));
        }
        total = applyCoupon(total, request.couponCode);
        total = total.add(calculateShipping(total, request.shippingAddress));
        total = total.add(calculateTax(total, request.shippingAddress));
        order.setTotal(total.setScale(2, RoundingMode.HALF_UP));
        order = orderRepository.save(order);

        // payment processing
        Payment payment = paymentService.charge(order, request.paymentMethodToken);
        if (!"SUCCEEDED".equals(payment.getStatus())) {
            order.setStatus("PAYMENT_FAILED");
            orderRepository.save(order);
            emailService.sendPaymentFailed(customer, order);
            return order;
        }

        // inventory updates
        for (OrderItem item : order.getItems()) {
            InventoryItem inv = inventoryRepository.findByProductId(item.getProduct().getId());
            inv.setQuantity(inv.getQuantity() - item.getQuantity());
            inventoryRepository.save(inv);
            if (inv.getQuantity() < 5) {
                emailService.sendLowStockAlert(item.getProduct(), inv.getQuantity());
            }
        }

        // email notification
        order.setStatus("CONFIRMED");
        orderRepository.save(order);
        emailService.sendOrderConfirmation(customer, order);
        return order;
    }

    private BigDecimal applyCoupon(BigDecimal total, String code) {
        if (code == null) return total;
        switch (code) {
            case "WELCOME10": return total.multiply(new BigDecimal("0.90"));
            case "FESTIVE20": return total.compareTo(new BigDecimal("2000")) > 0 ? total.multiply(new BigDecimal("0.80")) : total;
            case "FREESHIP": return total;
            default: return total;
        }
    }

    private BigDecimal calculateShipping(BigDecimal total, String address) {
        if (total.compareTo(new BigDecimal("999")) >= 0) return BigDecimal.ZERO;
        if (address != null && (address.contains("Delhi") || address.contains("Mumbai") || address.contains("Bengaluru"))) {
            return new BigDecimal("49");
        }
        return new BigDecimal("99");
    }

    private BigDecimal calculateTax(BigDecimal total, String address) {
        BigDecimal rate = new BigDecimal("0.18");
        if (address != null && address.contains("SEZ")) {
            rate = BigDecimal.ZERO;
        }
        return total.multiply(rate).setScale(2, RoundingMode.HALF_UP);
    }

    public void markPaid(Long orderId) {
        Order order = getById(orderId);
        order.setStatus("PAID");
        orderRepository.save(order);
    }

    @Transactional
    public Order cancelOrder(Long orderId) {
        Order order = getById(orderId);
        if ("SHIPPED".equals(order.getStatus()) || "DELIVERED".equals(order.getStatus())) {
            throw new IllegalStateException("Cannot cancel a shipped order");
        }
        if ("CONFIRMED".equals(order.getStatus()) || "PAID".equals(order.getStatus())) {
            paymentService.refund(order);
            for (OrderItem item : order.getItems()) {
                inventoryService.restock(item.getProduct().getId(), item.getQuantity());
            }
        }
        order.setStatus("CANCELLED");
        emailService.sendOrderCancelled(order.getCustomer(), order);
        return orderRepository.save(order);
    }

    public Order getById(Long id) {
        return orderRepository.findById(id).orElseThrow(() -> new IllegalArgumentException("Order not found"));
    }

    public List<Order> history(Long customerId) {
        return orderRepository.findByCustomerId(customerId);
    }

    public Order ship(Long orderId, String trackingNumber) {
        Order order = getById(orderId);
        if (!"CONFIRMED".equals(order.getStatus()) && !"PAID".equals(order.getStatus())) {
            throw new IllegalStateException("Order not ready to ship");
        }
        order.setStatus("SHIPPED");
        emailService.sendShippingUpdate(order.getCustomer(), order, trackingNumber);
        return orderRepository.save(order);
    }
}
