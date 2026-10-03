package com.shopverse.order;

import org.junit.jupiter.api.Test;
import static org.mockito.Mockito.*;

class OrderControllerTest {
    OrderService orderService = mock(OrderService.class);
    OrderController controller = new OrderController(orderService);

    @Test
    void cancelDelegates() {
        controller.cancel(1L);
        verify(orderService).cancelOrder(1L);
    }
}
