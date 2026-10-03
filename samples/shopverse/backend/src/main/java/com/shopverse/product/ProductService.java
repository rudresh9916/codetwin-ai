package com.shopverse.product;

import com.shopverse.inventory.InventoryService;
import org.springframework.stereotype.Service;
import java.math.BigDecimal;
import java.util.List;
import java.util.stream.Collectors;

/**
 * Catalogue browsing, search and pricing.
 */
@Service
public class ProductService {

    private final ProductRepository productRepository;
    private final InventoryService inventoryService;

    public ProductService(ProductRepository productRepository, InventoryService inventoryService) {
        this.productRepository = productRepository;
        this.inventoryService = inventoryService;
    }

    public List<Product> list(String category) {
        if (category == null || category.isBlank()) {
            return productRepository.findAll();
        }
        return productRepository.findByCategory(category);
    }

    public List<Product> search(String query) {
        return productRepository.findByNameContainingIgnoreCase(query);
    }

    public Product getById(Long id) {
        return productRepository.findById(id).orElseThrow(() -> new IllegalArgumentException("Product not found"));
    }

    public List<Product> listInStock() {
        return productRepository.findAll().stream()
                .filter(p -> inventoryService.getAvailable(p.getId()) > 0)
                .collect(Collectors.toList());
    }

    public BigDecimal priceFor(Long productId, int quantity) {
        Product p = getById(productId);
        BigDecimal total = p.getPrice().multiply(BigDecimal.valueOf(quantity));
        if (quantity >= 10) {
            total = total.multiply(new BigDecimal("0.90"));
        } else if (quantity >= 5) {
            total = total.multiply(new BigDecimal("0.95"));
        }
        return total;
    }

    public void updateRating(Long productId, double rating) {
        Product p = getById(productId);
        p.setRating(rating);
        productRepository.save(p);
    }
}
