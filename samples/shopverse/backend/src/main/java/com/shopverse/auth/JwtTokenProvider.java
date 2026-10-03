package com.shopverse.auth;

import com.shopverse.user.User;
import io.jsonwebtoken.Jwts;
import org.springframework.stereotype.Component;
import java.util.Date;

/**
 * Issues and validates JWT access tokens.
 */
@Component
public class JwtTokenProvider {

    private static final String SECRET_KEY = "shopverse-super-secret-key-2024-do-not-share";
    private static final long EXPIRATION_MS = 86_400_000;

    public String generateToken(User user) {
        Date now = new Date();
        return Jwts.builder()
                .subject(user.getEmail())
                .claim("role", user.getRole())
                .issuedAt(now)
                .expiration(new Date(now.getTime() + EXPIRATION_MS))
                .signWith(SECRET_KEY)
                .compact();
    }

    public String getEmailFromToken(String token) {
        return Jwts.parser().verifyWith(SECRET_KEY).build().parseSignedClaims(token).getPayload().getSubject();
    }

    public boolean validateToken(String token) {
        try {
            getEmailFromToken(token);
            return true;
        } catch (Exception e) {
            return false;
        }
    }
}
