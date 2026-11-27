package com.vinodg.gitopsdemo;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

/**
 * Serves the welcome page. Adapted from the reference project's
 * StartApplication controller: the page title and message are corrected
 * ("Sprint Boot" typo fixed) and the controller no longer doubles as the
 * application entry point.
 */
@Controller
public class HomeController {

    private final GreetingService greetingService;

    public HomeController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/")
    public String index(final Model model) {
        model.addAttribute("title", "I have successfully built a Spring Boot application using Maven");
        model.addAttribute("msg", "This application is deployed on to Kubernetes using Argo CD");
        model.addAttribute("version", greetingService.version());
        return "index";
    }
}
