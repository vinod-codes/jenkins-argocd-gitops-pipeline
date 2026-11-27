package com.vinodg.gitopsdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Entry point for the GitOps demo application.
 *
 * Routes (see the controllers in this package):
 *   GET /            - Thymeleaf welcome page
 *   GET /health      - JSON health status, used by Kubernetes probes
 *   GET /api/greet   - greeting message as JSON
 */
@SpringBootApplication
public class GitopsDemoApplication {

    public static final String VERSION = "1.0.0";

    public static void main(String[] args) {
        SpringApplication.run(GitopsDemoApplication.class, args);
    }
}
