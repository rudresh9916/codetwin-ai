package com.shopverse.product;

import com.shopverse.inventory.InventoryService;
import org.junit.jupiter.api.Test;
import static org.mockito.Mockito.*;
import static org.junit.jupiter.api.Assertions.*;

class ProductServiceTest {
    ProductRepository repo = mock(ProductRepository.class);
    InventoryService inventory = mock(InventoryService.class);
    ProductService productService = new ProductService(repo, inventory);

    @Test
    void searchDelegatesToRepository() {
        productService.search("phone");
        verify(repo).findByNameContainingIgnoreCase("phone");
    }
}
