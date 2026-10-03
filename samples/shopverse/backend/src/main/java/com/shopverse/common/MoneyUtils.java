package com.shopverse.common;

import java.math.BigDecimal;
import java.math.RoundingMode;

public final class MoneyUtils {
    private MoneyUtils() {}

    public static String formatInr(BigDecimal amount) {
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
}
