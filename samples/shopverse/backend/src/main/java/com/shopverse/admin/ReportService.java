package com.shopverse.admin;

import com.shopverse.order.Order;
import com.shopverse.order.OrderRepository;
import com.shopverse.user.UserService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

@Service
public class ReportService {

    private final JdbcTemplate jdbcTemplate;
    private final OrderRepository orderRepository;
    private final UserService userService;

    public ReportService(JdbcTemplate jdbcTemplate, OrderRepository orderRepository, UserService userService) {
        this.jdbcTemplate = jdbcTemplate;
        this.orderRepository = orderRepository;
        this.userService = userService;
    }

    public List<Map<String, Object>> salesByCategory(String from, String to) {
        String sql = "SELECT p.category, SUM(oi.quantity * oi.unit_price) AS revenue FROM order_items oi "
                + "JOIN products p ON p.id = oi.product_id JOIN orders o ON o.id = oi.order_id "
                + "WHERE o.created_at BETWEEN '" + from + "' AND '" + to + "' GROUP BY p.category";
        return jdbcTemplate.queryForList(sql);
    }

    public BigDecimal totalRevenue() {
        BigDecimal total = BigDecimal.ZERO;
        for (Order o : orderRepository.findAll()) {
            if ("CONFIRMED".equals(o.getStatus()) || "PAID".equals(o.getStatus()) || "SHIPPED".equals(o.getStatus())) {
                total = total.add(o.getTotal());
            }
        }
        return total;
    }

    public Map<String, Object> dashboard() {
        return Map.of(
            "activeUsers", userService.countActive(),
            "revenue", totalRevenue(),
            "pendingOrders", orderRepository.findByStatus("PENDING").size());
    }
}
