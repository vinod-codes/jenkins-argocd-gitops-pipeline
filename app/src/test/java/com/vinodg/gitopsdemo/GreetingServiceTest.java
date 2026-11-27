package com.vinodg.gitopsdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class GreetingServiceTest {

    private final GreetingService greetingService = new GreetingService();

    @Test
    void greetUsesProvidedName() {
        assertEquals("Hello, Vinod! Welcome to the GitOps demo.", greetingService.greet("Vinod"));
    }

    @Test
    void greetFallsBackToWorldForNull() {
        assertEquals("Hello, World! Welcome to the GitOps demo.", greetingService.greet(null));
    }

    @Test
    void greetFallsBackToWorldForBlank() {
        assertEquals("Hello, World! Welcome to the GitOps demo.", greetingService.greet("   "));
    }

    @Test
    void greetTrimsWhitespace() {
        assertEquals("Hello, Vinod! Welcome to the GitOps demo.", greetingService.greet("  Vinod  "));
    }

    @Test
    void versionIsSet() {
        assertEquals("1.0.0", greetingService.version());
        assertTrue(GreetingService.VERSION.matches("\\d+\\.\\d+\\.\\d+"));
    }
}
