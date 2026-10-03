package com.shopverse.user;

import org.junit.jupiter.api.Test;
import static org.mockito.Mockito.*;
import static org.junit.jupiter.api.Assertions.*;
import java.util.Optional;

class UserServiceTest {
    UserRepository repo = mock(UserRepository.class);
    UserService userService = new UserService(repo);

    @Test
    void findByEmailReturnsNullWhenMissing() {
        when(repo.findByEmail("a@b.c")).thenReturn(Optional.empty());
        assertNull(userService.findByEmail("a@b.c"));
    }

    @Test
    void createUserSaves() {
        when(repo.save(any())).thenAnswer(i -> i.getArgument(0));
        User u = userService.createUser("A", "a@b.c", "h");
        assertEquals("A", u.getName());
    }
}
