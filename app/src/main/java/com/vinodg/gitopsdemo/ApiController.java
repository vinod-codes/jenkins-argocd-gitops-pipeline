package com.vinodg.gitopsdemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * JSON endpoints. The reference project had no health endpoint, so the
 * Kubernetes probes in k8s/ and helm/ had nothing to call. This controller
 * adds one, plus a small greeting API used by the tests.
 */
@RestController
public class ApiController {

    private final GreetingService greetingService;

    public ApiController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of(
                "status", "UP",
                "app", "gitops-demo",
                "version", greetingService.version());
    }

    @GetMapping("/api/greet")
    public Map<String, String> greet(
            @RequestParam(defaultValue = "World") String name) {
        return Map.of("message", greetingService.greet(name));
    }
}
