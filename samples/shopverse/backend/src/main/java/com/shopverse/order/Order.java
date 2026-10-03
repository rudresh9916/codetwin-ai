package com.shopverse.order;

import com.shopverse.user.User;
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "orders")
public class Order {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @ManyToOne
    private User customer;
    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL)
    private List<OrderItem> items = new ArrayList<>();
    private BigDecimal total;
    private String status = "PENDING";
    private String shippingAddress;
    private LocalDateTime createdAt = LocalDateTime.now();

    public Long getId() { return id; }
    public User getCustomer() { return customer; }
    public void setCustomer(User c) { this.customer = c; }
    public List<OrderItem> getItems() { return items; }
    public BigDecimal getTotal() { return total; }
    public void setTotal(BigDecimal t) { this.total = t; }
    public String getStatus() { return status; }
    public void setStatus(String s) { this.status = s; }
    public String getShippingAddress() { return shippingAddress; }
    public void setShippingAddress(String a) { this.shippingAddress = a; }
    public LocalDateTime getCreatedAt() { return createdAt; }
}
