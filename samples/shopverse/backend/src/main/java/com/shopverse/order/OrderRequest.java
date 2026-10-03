package com.shopverse.order;

import java.util.List;

public class OrderRequest {
    public Long customerId;
    public List<Line> items;
    public String shippingAddress;
    public String paymentMethodToken;
    public String couponCode;

    public static class Line {
        public Long productId;
        public int quantity;
    }
}
