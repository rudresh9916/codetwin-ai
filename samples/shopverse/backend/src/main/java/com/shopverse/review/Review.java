package com.shopverse.review;

import jakarta.persistence.*;

@Entity
@Table(name = "reviews")
public class Review {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    private Long productId;
    private Long userId;
    private int stars;
    private String comment;

    public Long getProductId() { return productId; }
    public int getStars() { return stars; }
    public String getComment() { return comment; }
}
