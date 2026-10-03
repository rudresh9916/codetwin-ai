package com.shopverse.payment;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(name = "payments")
public class Payment {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    private Long orderId;
    private BigDecimal amount;
    private String currency = "INR";
    private String status;
    private String providerReference;
    private int attempts;
    private LocalDateTime processedAt;

    public Long getId() { return id; }
    public Long getOrderId() { return orderId; }
    public void setOrderId(Long id) { this.orderId = id; }
    public BigDecimal getAmount() { return amount; }
    public void setAmount(BigDecimal a) { this.amount = a; }
    public String getStatus() { return status; }
    public void setStatus(String s) { this.status = s; }
    public String getProviderReference() { return providerReference; }
    public void setProviderReference(String r) { this.providerReference = r; }
    public int getAttempts() { return attempts; }
    public void setAttempts(int a) { this.attempts = a; }
    public void setProcessedAt(LocalDateTime t) { this.processedAt = t; }
}
