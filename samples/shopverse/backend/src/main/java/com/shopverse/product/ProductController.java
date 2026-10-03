package com.shopverse.product;

import org.springframework.web.bind.annotation.*;
import java.util.List;

/**
 * Public catalogue endpoints.
 */
@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping
    public List<Product> list(@RequestParam(required = false) String category) {
        return productService.list(category);
    }

    @GetMapping("/search")
    public List<Product> search(@RequestParam String q) {
        return productService.search(q);
    }

    @GetMapping("/{id}")
    public Product get(@PathVariable Long id) {
        return productService.getById(id);
    }

    @GetMapping("/in-stock")
    public List<Product> inStock() {
        return productService.listInStock();
    }
}
