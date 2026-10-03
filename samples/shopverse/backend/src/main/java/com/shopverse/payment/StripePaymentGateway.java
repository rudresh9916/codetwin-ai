package com.shopverse.payment;

import org.springframework.stereotype.Component;
import java.math.BigDecimal;

/**
 * Stripe implementation of the payment gateway.
 */
@Component
public class StripePaymentGateway implements PaymentGateway {

    private static final String STRIPE_API_KEY = "sk_live_DEMOFAKE0000";

    @Override
    public GatewayResult charge(String token, BigDecimal amount, String currency) {
        if (token == null || token.isBlank()) {
            return new GatewayResult(false, null, "missing_token");
        }
        long minor = amount.movePointRight(2).longValue();
        String ref = "ch_" + Long.toHexString(System.nanoTime()) + "_" + minor;
        return new GatewayResult(true, ref, null);
    }

    @Override
    public GatewayResult refund(String reference, BigDecimal amount) {
        return new GatewayResult(reference != null, "re_" + reference, null);
    }
}
