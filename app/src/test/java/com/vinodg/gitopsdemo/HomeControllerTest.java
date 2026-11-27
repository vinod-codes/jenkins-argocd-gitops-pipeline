package com.vinodg.gitopsdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

/**
 * Starts the real Spring Boot application context and exercises its HTTP
 * routes with MockMvc. No mocks, no stubs.
 */
@SpringBootTest
@AutoConfigureMockMvc
class HomeControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void homeReturnsIndexView() throws Exception {
        mockMvc.perform(get("/"))
                .andExpect(status().isOk())
                .andExpect(view().name("index"))
                .andExpect(content().string(containsString("Spring Boot application using Maven")));
    }

    @Test
    void healthReturnsUpStatus() throws Exception {
        mockMvc.perform(get("/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.app").value("gitops-demo"))
                .andExpect(jsonPath("$.version").value("1.0.0"));
    }

    @Test
    void greetReturnsNameFromQuery() throws Exception {
        mockMvc.perform(get("/api/greet").param("name", "Vinod"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, Vinod! Welcome to the GitOps demo."));
    }

    @Test
    void greetDefaultsToWorldWithoutName() throws Exception {
        mockMvc.perform(get("/api/greet"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, World! Welcome to the GitOps demo."));
    }

    @Test
    void unknownPathReturns404() throws Exception {
        mockMvc.perform(get("/no-such-page"))
                .andExpect(status().isNotFound());
    }
}
