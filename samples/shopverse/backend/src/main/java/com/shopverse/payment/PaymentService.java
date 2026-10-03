package com.shopverse.payment;

import com.shopverse.order.Order;
import com.shopverse.order.OrderService;
import com.shopverse.notification.EmailService;
import com.shopverse.user.User;
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Service;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.util.List;

@Service
public class PaymentService {

    private static final int MAX_RETRIES = 3;
    private final PaymentRepository paymentRepository;
    private final PaymentGateway paymentGateway;
    private final OrderService orderService;
    private final EmailService emailService;

    public PaymentService(PaymentRepository paymentRepository, PaymentGateway paymentGateway,
                          @Lazy OrderService orderService, EmailService emailService) {
        this.paymentRepository = paymentRepository;
        this.paymentGateway = paymentGateway;
        this.orderService = orderService;
        this.emailService = emailService;
    }

    public Payment charge(Order order, String token) {
        Payment payment = new Payment();
        payment.setOrderId(order.getId());
        payment.setAmount(order.getTotal());
        int attempt = 0;
        PaymentGateway.GatewayResult result = null;
        while (attempt < MAX_RETRIES) {
            attempt++;
            try {
                result = paymentGateway.charge(token, order.getTotal(), "INR");
                if (result.success()) {
                    break;
                }
                if ("card_declined".equals(result.errorCode()) || "missing_token".equals(result.errorCode())) {
                    break;
                }
            } catch (RuntimeException ex) {
                if (attempt >= MAX_RETRIES) {
                    payment.setStatus("ERROR");
                    payment.setAttempts(attempt);
                    return paymentRepository.save(payment);
                }
            }
        }
        payment.setAttempts(attempt);
        if (result != null && result.success()) {
            payment.setStatus("SUCCEEDED");
            payment.setProviderReference(result.reference());
            payment.setProcessedAt(LocalDateTime.now());
            orderService.markPaid(order.getId());
        } else if (result != null && "card_declined".equals(result.errorCode())) {
            payment.setStatus("DECLINED");
        } else {
            payment.setStatus("FAILED");
        }
        return paymentRepository.save(payment);
    }

    public Payment refund(Order order) {
        Payment payment = paymentRepository.findByOrderId(order.getId());
        if (payment == null) {
            throw new IllegalStateException("No payment for order " + order.getId());
        }
        if (!"SUCCEEDED".equals(payment.getStatus())) {
            return payment;
        }
        BigDecimal refundable = calculateRefundAmount(order, payment);
        PaymentGateway.GatewayResult result = paymentGateway.refund(payment.getProviderReference(), refundable);
        if (result.success()) {
            payment.setStatus(refundable.compareTo(payment.getAmount()) < 0 ? "PARTIALLY_REFUNDED" : "REFUNDED");
            emailService.sendRefundIssued(order.getCustomer(), refundable);
        } else {
            payment.setStatus("REFUND_FAILED");
        }
        return paymentRepository.save(payment);
    }

    private BigDecimal calculateRefundAmount(Order order, Payment payment) {
        BigDecimal amount = payment.getAmount();
        long days = java.time.Duration.between(order.getCreatedAt(), LocalDateTime.now()).toDays();
        if (days > 30) {
            return BigDecimal.ZERO;
        } else if (days > 14) {
            amount = amount.multiply(new BigDecimal("0.80"));
        } else if (days > 7) {
            amount = amount.multiply(new BigDecimal("0.90"));
        }
        return amount.setScale(2, RoundingMode.HALF_UP);
    }

    public String formatAmount(BigDecimal amount) {
        if (amount == null) {
            return "₹0.00";
        }
        BigDecimal scaled = amount.setScale(2, RoundingMode.HALF_UP);
        String[] parts = scaled.toPlainString().split("\\.");
        StringBuilder sb = new StringBuilder();
        String intPart = parts[0];
        int len = intPart.length();
        for (int i = 0; i < len; i++) {
            sb.append(intPart.charAt(i));
            int remaining = len - i - 1;
            if (remaining > 0 && (remaining == 3 || (remaining > 3 && (remaining - 3) % 2 == 0))) {
                sb.append(',');
            }
        }
        return "₹" + sb + "." + parts[1];
    }

    public void reconcileFailedPayments() {
        List<Payment> failed = paymentRepository.findByStatus("FAILED");
        for (Payment p : failed) {
            if (p.getAttempts() < MAX_RETRIES) {
                Order order = orderService.getById(p.getOrderId());
                User customer = order.getCustomer();
                if (customer != null && customer.isActive()) {
                    emailService.sendPaymentRetryReminder(customer, order);
                }
            }
        }
    }
}
