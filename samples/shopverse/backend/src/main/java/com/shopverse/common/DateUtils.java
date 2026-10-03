package com.shopverse.common;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

public final class DateUtils {
    private static final DateTimeFormatter FMT = DateTimeFormatter.ofPattern("dd MMM yyyy, HH:mm");
    private DateUtils() {}
    public static String pretty(LocalDateTime t) { return t == null ? "" : t.format(FMT); }
}
