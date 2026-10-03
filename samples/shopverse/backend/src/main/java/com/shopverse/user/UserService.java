package com.shopverse.user;

import org.springframework.stereotype.Service;
import java.time.LocalDateTime;
import java.util.List;

/**
 * Business logic for user accounts and profiles.
 */
@Service
public class UserService {

    private final UserRepository userRepository;

    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    public User findByEmail(String email) {
        return userRepository.findByEmail(email).orElse(null);
    }

    public User getById(Long id) {
        return userRepository.findById(id).orElseThrow(() -> new IllegalArgumentException("User not found"));
    }

    public User createUser(String name, String email, String passwordHash) {
        User user = new User();
        user.setName(name);
        user.setEmail(email);
        user.setPasswordHash(passwordHash);
        return userRepository.save(user);
    }

    public User updateProfile(Long id, String name, String email) {
        User user = getById(id);
        if (name != null && !name.isBlank()) {
            user.setName(name);
        }
        if (email != null && !email.isBlank() && !email.equals(user.getEmail())) {
            if (findByEmail(email) != null) {
                throw new IllegalArgumentException("Email in use");
            }
            user.setEmail(email);
        }
        return userRepository.save(user);
    }

    public void recordLogin(User user) {
        user.setLastLoginAt(LocalDateTime.now());
        userRepository.save(user);
    }

    public void deactivate(Long id) {
        User user = getById(id);
        user.setActive(false);
        userRepository.save(user);
    }

    public List<User> listAll() {
        return userRepository.findAll();
    }

    public long countActive() {
        return userRepository.countByActiveTrue();
    }
}
