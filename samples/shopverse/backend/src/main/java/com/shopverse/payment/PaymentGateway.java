package com.shopverse.payment;

import java.math.BigDecimal;

/**
 * Abstraction over an external payment provider.
 */
public interface PaymentGateway {
    GatewayResult charge(String token, BigDecimal amount, String currency);
    GatewayResult refund(String reference, BigDecimal amount);

    record GatewayResult(boolean success, String reference, String errorCode) {}
}
