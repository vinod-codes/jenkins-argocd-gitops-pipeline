package com.vinodg.gitopsdemo;

import org.springframework.stereotype.Service;

/**
 * Small piece of business logic kept separate from the HTTP layer so it can
 * be unit tested without starting a server.
 */
@Service
public class GreetingService {

    public static final String VERSION = "1.0.0";

    public String greet(String name) {
        String safeName = (name == null || name.isBlank()) ? "World" : name.trim();
        return "Hello, " + safeName + "! Welcome to the GitOps demo.";
    }

    public String version() {
        return VERSION;
    }
}
