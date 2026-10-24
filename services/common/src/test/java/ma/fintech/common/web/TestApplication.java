package ma.fintech.common.web;

import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import ma.fintech.common.security.AuthorizationRules;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/** A fake service: the common auto-configurations plus a few endpoints that exercise them. */
@SpringBootApplication
class TestApplication {

    @Bean
    AuthorizationRules adminRules() {
        return rules -> rules.requestMatchers("/api/v1/test/admin").hasRole("ADMIN");
    }

    record Item(@NotBlank String name, @Positive int amount) {
    }

    @RestController
    static class TestEndpoints {

        @GetMapping({"/actuator/health/liveness", "/actuator/health/readiness"})
        Map<String, String> probe() {
            return Map.of("status", "UP");
        }

        @GetMapping({"/api/v1/test/me", "/api/v1/test/admin"})
        List<String> authorities(Authentication authentication) {
            return authentication.getAuthorities().stream().map(GrantedAuthority::getAuthority).toList();
        }

        @PostMapping("/api/v1/test/items")
        Item create(@Valid @RequestBody Item item) {
            return item;
        }

        @GetMapping("/api/v1/test/missing")
        void missing() {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Customer 42 not found");
        }

        @GetMapping("/api/v1/test/boom")
        void boom() {
            throw new IllegalStateException("jdbc:postgresql://secret-host password=hunter2");
        }
    }
}
