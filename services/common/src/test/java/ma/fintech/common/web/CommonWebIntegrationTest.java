package ma.fintech.common.web;

import java.time.Instant;
import java.util.List;

import ma.fintech.common.correlation.CorrelationId;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.matchesPattern;
import static org.hamcrest.Matchers.not;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CommonWebIntegrationTest {

    private static final String CORRELATION_ID = "3f1c2b4a-9d8e-4f00-a1b2-c3d4e5f60718";

    @Autowired
    MockMvc mvc;

    @MockitoBean
    JwtDecoder jwtDecoder;

    @BeforeEach
    void tokens() {
        given(jwtDecoder.decode(anyString())).willAnswer(call -> switch (call.<String>getArgument(0)) {
            case "admin" -> jwt("ADMIN");
            case "analyste" -> jwt("ANALYSTE");
            default -> throw new BadJwtException("bad signature");
        });
    }

    @Nested
    class Security {

        @ParameterizedTest
        @ValueSource(strings = {"/actuator/health/liveness", "/actuator/health/readiness"})
        void probesAreOpen(String path) throws Exception {
            mvc.perform(get(path)).andExpect(status().isOk());
        }

        @Test
        void rolesClaimBecomesRoleAuthorities() throws Exception {
            mvc.perform(get("/api/v1/test/me").header(HttpHeaders.AUTHORIZATION, "Bearer analyste"))
                    .andExpect(status().isOk())
                    // Security 7 also adds FACTOR_BEARER (how the user authenticated).
                    .andExpect(jsonPath("$", hasItem("ROLE_ANALYSTE")))
                    .andExpect(jsonPath("$", not(hasItem("ANALYSTE"))));
        }

        @Test
        void missingTokenIs401ProblemDetail() throws Exception {
            mvc.perform(get("/api/v1/test/me").header(CorrelationId.HEADER, CORRELATION_ID))
                    .andExpect(status().isUnauthorized())
                    .andExpect(header().string(HttpHeaders.WWW_AUTHENTICATE, containsString("Bearer")))
                    .andExpect(content().contentType(MediaType.APPLICATION_PROBLEM_JSON))
                    .andExpect(jsonPath("$.status").value(401))
                    .andExpect(jsonPath("$.correlationId").value(CORRELATION_ID));
        }

        @Test
        void writeWithoutTokenIs401NotCsrf403() throws Exception {
            mvc.perform(post("/api/v1/test/items").contentType(MediaType.APPLICATION_JSON)
                            .content("{\"name\":\"x\",\"amount\":1}"))
                    .andExpect(status().isUnauthorized());
        }

        @Test
        void invalidTokenIs401() throws Exception {
            mvc.perform(get("/api/v1/test/me").header(HttpHeaders.AUTHORIZATION, "Bearer forged"))
                    .andExpect(status().isUnauthorized())
                    .andExpect(content().contentType(MediaType.APPLICATION_PROBLEM_JSON));
        }

        @Test
        void serviceRulesApply() throws Exception {
            mvc.perform(get("/api/v1/test/admin").header(HttpHeaders.AUTHORIZATION, "Bearer admin"))
                    .andExpect(status().isOk());
        }

        @Test
        void wrongRoleIs403ProblemDetail() throws Exception {
            mvc.perform(get("/api/v1/test/admin").header(HttpHeaders.AUTHORIZATION, "Bearer analyste"))
                    .andExpect(status().isForbidden())
                    .andExpect(content().contentType(MediaType.APPLICATION_PROBLEM_JSON))
                    .andExpect(jsonPath("$.status").value(403))
                    .andExpect(jsonPath("$.instance").value("/api/v1/test/admin"));
        }
    }

    @Nested
    class ProblemDetails {

        @Test
        void validationErrorListsFields() throws Exception {
            mvc.perform(post("/api/v1/test/items").header(HttpHeaders.AUTHORIZATION, "Bearer admin")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content("{\"name\":\"\",\"amount\":-5}"))
                    .andExpect(status().isBadRequest())
                    .andExpect(content().contentType(MediaType.APPLICATION_PROBLEM_JSON))
                    .andExpect(jsonPath("$.errors.length()").value(2))
                    .andExpect(jsonPath("$.errors[?(@.field == 'name')].message").exists())
                    .andExpect(jsonPath("$.errors[?(@.field == 'amount')].message").exists());
        }

        @Test
        void errorCarriesInstanceAndRequestCorrelationId() throws Exception {
            mvc.perform(get("/api/v1/test/missing").header(HttpHeaders.AUTHORIZATION, "Bearer admin")
                            .header(CorrelationId.HEADER, CORRELATION_ID))
                    .andExpect(status().isNotFound())
                    .andExpect(header().string(CorrelationId.HEADER, CORRELATION_ID))
                    .andExpect(jsonPath("$.title").value("Not Found"))
                    .andExpect(jsonPath("$.detail").value("Customer 42 not found"))
                    .andExpect(jsonPath("$.instance").value("/api/v1/test/missing"))
                    .andExpect(jsonPath("$.correlationId").value(CORRELATION_ID));
        }

        @Test
        void unexpectedErrorIs500WithoutLeakingInternals() throws Exception {
            mvc.perform(get("/api/v1/test/boom").header(HttpHeaders.AUTHORIZATION, "Bearer admin"))
                    .andExpect(status().isInternalServerError())
                    .andExpect(content().contentType(MediaType.APPLICATION_PROBLEM_JSON))
                    .andExpect(jsonPath("$.detail", not(containsString("hunter2"))))
                    .andExpect(jsonPath("$.correlationId", matchesPattern(CorrelationId.UUID_PATTERN)));
        }
    }

    private static Jwt jwt(String role) {
        return Jwt.withTokenValue("token")
                .header("alg", "RS256")
                .subject("user-1")
                .claim("roles", List.of(role))
                .issuedAt(Instant.now())
                .expiresAt(Instant.now().plusSeconds(900))
                .build();
    }
}
