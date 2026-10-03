package com.shopverse.inventory;

import org.springframework.stereotype.Service;

/**
 * Stock levels per product.
 */
@Service
public class InventoryService {

    private final InventoryRepository inventoryRepository;

    public InventoryService(InventoryRepository inventoryRepository) {
        this.inventoryRepository = inventoryRepository;
    }

    public int getAvailable(Long productId) {
        InventoryItem item = inventoryRepository.findByProductId(productId);
        return item == null ? 0 : item.getQuantity();
    }

    public void restock(Long productId, int quantity) {
        InventoryItem item = inventoryRepository.findByProductId(productId);
        if (item != null) {
            item.setQuantity(item.getQuantity() + quantity);
            inventoryRepository.save(item);
        }
    }
}
