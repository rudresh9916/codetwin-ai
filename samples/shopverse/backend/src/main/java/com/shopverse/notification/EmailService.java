package com.shopverse.notification;

import com.shopverse.order.Order;
import com.shopverse.product.Product;
import com.shopverse.user.User;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;
import java.math.BigDecimal;

/**
 * Sends transactional emails.
 */
@Service
public class EmailService {

    private final JavaMailSender mailSender;

    public EmailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    private void send(String to, String subject, String body) {
        SimpleMailMessage msg = new SimpleMailMessage();
        msg.setTo(to);
        msg.setSubject(subject);
        msg.setText(body);
        mailSender.send(msg);
    }

    public void sendWelcomeEmail(User user) { send(user.getEmail(), "Welcome to ShopVerse", "Hi " + user.getName()); }
    public void sendPasswordReset(User user, String token) { send(user.getEmail(), "Reset your password", "Token: " + token); }
    public void sendOrderConfirmation(User user, Order order) { send(user.getEmail(), "Order #" + order.getId() + " confirmed", "Total: " + order.getTotal()); }
    public void sendPaymentFailed(User user, Order order) { send(user.getEmail(), "Payment failed", "Order #" + order.getId()); }
    public void sendOrderCancelled(User user, Order order) { send(user.getEmail(), "Order cancelled", "Order #" + order.getId()); }
    public void sendShippingUpdate(User user, Order order, String tracking) { send(user.getEmail(), "Your order shipped", tracking); }
    public void sendRefundIssued(User user, BigDecimal amount) { send(user.getEmail(), "Refund issued", "Amount: " + amount); }
    public void sendPaymentRetryReminder(User user, Order order) { send(user.getEmail(), "Complete your payment", "Order #" + order.getId()); }
    public void sendLowStockAlert(Product product, int qty) { send("ops@shopverse.in", "Low stock: " + product.getName(), "Remaining: " + qty); }
}
