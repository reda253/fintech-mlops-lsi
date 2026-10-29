package ma.fintech.auth.api;

import java.util.Set;

import com.jayway.jsonpath.JsonPath;
import ma.fintech.auth.TestcontainersConfig;
import ma.fintech.auth.domain.User;
import ma.fintech.auth.domain.User.Role;
import ma.fintech.auth.repository.RefreshTokenRepository;
import ma.fintech.auth.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;

import static org.assertj.core.api.Assertions.assertThat;
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

    User analyst;

    @BeforeEach
    void setUp() {
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

    @Test
    void invalidBodyIs400() throws Exception {
        login("ab", "short").andExpect(status().isBadRequest());
    }

    private ResultActions login(String username, String password) throws Exception {
        return mvc.perform(post("/api/v1/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"" + username + "\",\"password\":\"" + password + "\"}"));
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
