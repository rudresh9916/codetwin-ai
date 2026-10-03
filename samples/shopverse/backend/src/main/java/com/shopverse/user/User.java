package com.shopverse.user;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * A registered ShopVerse customer or administrator.
 */
@Entity
@Table(name = "users")
public class User {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    private String name;
    @Column(unique = true)
    private String email;
    private String passwordHash;
    private String role = "CUSTOMER";
    private boolean active = true;
    private LocalDateTime lastLoginAt;

    public Long getId() { return id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public String getPasswordHash() { return passwordHash; }
    public void setPasswordHash(String hash) { this.passwordHash = hash; }
    public String getRole() { return role; }
    public boolean isActive() { return active; }
    public void setActive(boolean active) { this.active = active; }
    public void setLastLoginAt(LocalDateTime t) { this.lastLoginAt = t; }
}
