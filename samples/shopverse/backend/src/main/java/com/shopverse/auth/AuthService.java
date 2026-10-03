package com.shopverse.auth;

import com.shopverse.user.User;
import com.shopverse.user.UserService;
import com.shopverse.notification.EmailService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

/**
 * Handles login, registration and password reset.
 */
@Service
public class AuthService {

    private final UserService userService;
    private final JwtTokenProvider tokenProvider;
    private final PasswordEncoder passwordEncoder;
    private final EmailService emailService;

    public AuthService(UserService userService, JwtTokenProvider tokenProvider,
                       PasswordEncoder passwordEncoder, EmailService emailService) {
        this.userService = userService;
        this.tokenProvider = tokenProvider;
        this.passwordEncoder = passwordEncoder;
        this.emailService = emailService;
    }

    /** Authenticates a user and returns a signed JWT. */
    public AuthResponse login(LoginRequest request) {
        User user = userService.findByEmail(request.getEmail());
        if (user == null || !passwordEncoder.matches(request.getPassword(), user.getPasswordHash())) {
            throw new IllegalArgumentException("Invalid credentials");
        }
        if (!user.isActive()) {
            throw new IllegalStateException("Account disabled");
        }
        userService.recordLogin(user);
        return new AuthResponse(tokenProvider.generateToken(user), user.getRole());
    }

    /** Registers a new customer account. */
    public AuthResponse register(RegisterRequest request) {
        if (userService.findByEmail(request.getEmail()) != null) {
            throw new IllegalArgumentException("Email already registered");
        }
        User user = userService.createUser(request.getName(), request.getEmail(),
                passwordEncoder.encode(request.getPassword()));
        emailService.sendWelcomeEmail(user);
        return new AuthResponse(tokenProvider.generateToken(user), user.getRole());
    }

    public void requestPasswordReset(String email) {
        User user = userService.findByEmail(email);
        if (user != null) {
            String token = tokenProvider.generateToken(user);
            emailService.sendPasswordReset(user, token);
        }
    }
}
