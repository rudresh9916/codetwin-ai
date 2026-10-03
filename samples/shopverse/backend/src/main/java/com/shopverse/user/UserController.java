package com.shopverse.user;

import org.springframework.web.bind.annotation.*;

/**
 * Profile endpoints for the signed-in user.
 */
@RestController
@RequestMapping("/api/users")
public class UserController {

    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping("/{id}")
    public UserDto getUser(@PathVariable Long id) {
        return UserDto.from(userService.getById(id));
    }

    @PutMapping("/{id}")
    public UserDto updateProfile(@PathVariable Long id, @RequestBody UserDto body) {
        return UserDto.from(userService.updateProfile(id, body.name(), body.email()));
    }

    @DeleteMapping("/{id}")
    public void deactivate(@PathVariable Long id) {
        userService.deactivate(id);
    }
}
