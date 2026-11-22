package ma.fintech.auth.api;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.jayway.jsonpath.JsonPath;
import ma.fintech.auth.TestcontainersConfig;
import ma.fintech.auth.domain.RefreshToken;
import ma.fintech.auth.domain.User;
import ma.fintech.auth.domain.User.Role;
import ma.fintech.auth.repository.RefreshTokenRepository;
import ma.fintech.auth.repository.UserRepository;
import ma.fintech.auth.service.AuthService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.tuple;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(TestcontainersConfig.class)
class AuthControllerTest {

    @Autowired MockMvc mvc;
    @Autowired UserRepository users;
    @Autowired RefreshTokenRepository refreshTokens;
    @Autowired PasswordEncoder passwordEncoder;
    @Autowired JwtDecoder jwtDecoder;

    @Autowired JdbcClient jdbc;

    User analyst;

    @BeforeEach
    void setUp() {
        jdbc.sql("DELETE FROM outbox_events").update();
        refreshTokens.deleteAll();
        users.deleteAll();
        analyst = users.save(new User("analyste1", passwordEncoder.encode("correct-horse"), Set.of(Role.ANALYSTE)));
        User disabled = new User("disabled1", passwordEncoder.encode("correct-horse"), Set.of(Role.ADMIN));
        disabled.setEnabled(false);
        users.save(disabled);
    }

    @Test
    void loginIssuesSignedAccessTokenAndStoresOnlyTheRefreshTokenHash() throws Exception {
        String body = login("analyste1", "correct-horse")
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tokenType").value("Bearer"))
                .andExpect(jsonPath("$.expiresIn").value(900))
                .andExpect(jsonPath("$.refreshExpiresIn").value(604800))
                .andReturn().getResponse().getContentAsString();

        Jwt jwt = jwtDecoder.decode(JsonPath.read(body, "$.accessToken"));
        assertThat(jwt.getHeaders()).containsKey("kid");
        assertThat(jwt.getSubject()).isEqualTo(analyst.getId().toString());
        assertThat(jwt.getClaimAsString("iss")).isEqualTo("fintech-auth");
        assertThat(jwt.getClaimAsString("preferred_username")).isEqualTo("analyste1");
        assertThat(jwt.getClaimAsStringList("roles")).containsExactly("ANALYSTE");
        assertThat(jwt.getExpiresAt()).isEqualTo(jwt.getIssuedAt().plusSeconds(900));

        String refreshToken = JsonPath.read(body, "$.refreshToken");
        assertThat(refreshTokens.findAll()).singleElement().satisfies(stored -> {
            assertThat(stored.getTokenHash()).hasSize(64).isNotEqualTo(refreshToken);
            assertThat(stored.getUserId()).isEqualTo(analyst.getId());
        });
    }

    @Test
    void wrongPasswordUnknownUserAndDisabledAccountAreIndistinguishable() throws Exception {
        String wrongPassword = rejected("analyste1", "wrong-password");
        assertThat(rejected("nobody", "correct-horse")).isEqualTo(wrongPassword);
        assertThat(rejected("disabled1", "correct-horse")).isEqualTo(wrongPassword);
        assertThat(refreshTokens.count()).isZero();
    }

    /** Every attempt is written to the outbox in the same transaction (contracts/events.md, auth.login.*). */
    @Test
    void everyLoginAttemptLeavesOneLoginEventWithoutThePassword() throws Exception {
        login("analyste1", "correct-horse").andExpect(status().isOk());
        login("analyste1", "wrong-password").andExpect(status().isUnauthorized());
        login("nobody", "correct-horse").andExpect(status().isUnauthorized());
        login("disabled1", "correct-horse").andExpect(status().isUnauthorized());

        List<Map<String, Object>> events = jdbc.sql("""
                        SELECT event_type, payload::text AS payload,
                               payload ->> 'actor' AS actor,
                               payload -> 'payload' ->> 'username' AS username,
                               payload -> 'payload' ->> 'userId' AS user_id,
                               payload -> 'payload' ->> 'reason' AS reason
                        FROM outbox_events ORDER BY created_at""")
                .query().listOfRows();

        assertThat(events).extracting(e -> e.get("event_type"), e -> e.get("username"), e -> e.get("reason"))
                .containsExactly(
                        tuple("auth.login.succeeded", "analyste1", null),
                        tuple("auth.login.failed", "analyste1", "BAD_CREDENTIALS"),
                        tuple("auth.login.failed", "nobody", "BAD_CREDENTIALS"),
                        tuple("auth.login.failed", "disabled1", "DISABLED"));
        assertThat(events.get(0).get("user_id")).isEqualTo(analyst.getId().toString());
        assertThat(events.get(2).get("user_id")).as("unknown user").isNull();
        assertThat(events).allSatisfy(e -> {
            assertThat(e.get("actor")).isEqualTo(e.get("username"));
            assertThat((String) e.get("payload")).doesNotContain("correct-horse", "wrong-password");
        });
    }

    @Test
    void invalidBodyIs400() throws Exception {
        login("ab", "short").andExpect(status().isBadRequest());
        refresh("").andExpect(status().isBadRequest());
    }

    @Test
    void refreshRotatesAndReuseRevokesTheWholeFamily() throws Exception {
        String first = refreshTokenOf(login("analyste1", "correct-horse"));

        String second = refreshTokenOf(refresh(first).andExpect(status().isOk()));
        assertThat(second).isNotEqualTo(first);

        // Replaying the rotated token = stolen copy: rejected, and the legitimate new token dies with it.
        refresh(first).andExpect(status().isUnauthorized());
        refresh(second).andExpect(status().isUnauthorized());
    }

    @Test
    void unknownExpiredOrDisabledRefreshIs401() throws Exception {
        refresh("never-issued").andExpect(status().isUnauthorized());

        refreshTokens.save(new RefreshToken(analyst.getId(), AuthService.sha256("expired"), Instant.now().minusSeconds(1)));
        refresh("expired").andExpect(status().isUnauthorized());

        String token = refreshTokenOf(login("analyste1", "correct-horse"));
        analyst.setEnabled(false);
        users.save(analyst);
        refresh(token).andExpect(status().isUnauthorized());
    }

    private ResultActions login(String username, String password) throws Exception {
        return mvc.perform(post("/api/v1/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"" + username + "\",\"password\":\"" + password + "\"}"));
    }

    private ResultActions refresh(String refreshToken) throws Exception {
        return mvc.perform(post("/api/v1/auth/refresh")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"refreshToken\":\"" + refreshToken + "\"}"));
    }

    private static String refreshTokenOf(ResultActions result) throws Exception {
        return JsonPath.read(result.andReturn().getResponse().getContentAsString(), "$.refreshToken");
    }

    /** Problem Details body of a rejected login, minus the per-request fields. */
    private String rejected(String username, String password) throws Exception {
        String body = login(username, password)
                .andExpect(status().isUnauthorized())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON))
                .andReturn().getResponse().getContentAsString();
        return JsonPath.read(body, "$.title") + "|" + JsonPath.read(body, "$.detail");
    }
}
