package com.shopverse.review;

import com.shopverse.product.ProductService;
import org.springframework.web.bind.annotation.*;
import java.util.List;

@RestController
@RequestMapping("/api/reviews")
public class ReviewController {

    private final ReviewRepository reviewRepository;
    private final ProductService productService;

    public ReviewController(ReviewRepository reviewRepository, ProductService productService) {
        this.reviewRepository = reviewRepository;
        this.productService = productService;
    }

    @GetMapping("/product/{productId}")
    public List<Review> forProduct(@PathVariable Long productId) {
        return reviewRepository.findByProductId(productId);
    }

    @PostMapping
    public Review create(@RequestBody Review review) {
        Review saved = reviewRepository.save(review);
        List<Review> all = reviewRepository.findByProductId(review.getProductId());
        double avg = all.stream().mapToInt(Review::getStars).average().orElse(0);
        productService.updateRating(review.getProductId(), avg);
        return saved;
    }
}
