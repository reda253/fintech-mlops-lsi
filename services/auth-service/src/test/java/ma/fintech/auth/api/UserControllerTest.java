package ma.fintech.auth.api;

import java.util.Set;

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
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.JwtRequestPostProcessor;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(TestcontainersConfig.class)
class UserControllerTest {

    @Autowired MockMvc mvc;
    @Autowired UserRepository users;
    @Autowired RefreshTokenRepository refreshTokens;
    @Autowired PasswordEncoder passwordEncoder;

    User admin;
    User analyst;

    @BeforeEach
    void setUp() {
        refreshTokens.deleteAll();
        users.deleteAll();
        admin = users.save(new User("boss", passwordEncoder.encode("admin-password"), Set.of(Role.ADMIN)));
        analyst = users.save(new User("analyste1", passwordEncoder.encode("correct-horse"), Set.of(Role.ANALYSTE)));
    }

    @Test
    void meReturnsTheCallerWithoutThePasswordHash() throws Exception {
        mvc.perform(get("/api/v1/auth/me").with(as(analyst, "ANALYSTE")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("analyste1"))
                .andExpect(jsonPath("$.roles[0]").value("ANALYSTE"))
                .andExpect(jsonPath("$.passwordHash").doesNotExist());
    }

    @Test
    void usersEndpointsAreAdminOnly() throws Exception {
        mvc.perform(get("/api/v1/auth/users")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/v1/auth/users").with(as(analyst, "ANALYSTE"))).andExpect(status().isForbidden());
    }

    @Test
    void adminCreatesListsFiltersAndRejectsDuplicates() throws Exception {
        String body = "{\"username\":\"sim2\",\"password\":\"simulator-pass\",\"roles\":[\"SIMULATEUR\"]}";
        mvc.perform(post("/api/v1/auth/users").with(as(admin, "ADMIN"))
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isCreated())
                .andExpect(header().string("Location", startsWith("/api/v1/auth/users/")))
                .andExpect(jsonPath("$.roles[0]").value("SIMULATEUR"));
        mvc.perform(post("/api/v1/auth/users").with(as(admin, "ADMIN"))
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isConflict());

        mvc.perform(get("/api/v1/auth/users?role=SIMULATEUR").with(as(admin, "ADMIN")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content.length()").value(1))
                .andExpect(jsonPath("$.content[0].username").value("sim2"))
                .andExpect(jsonPath("$.page.totalElements").value(1));
    }

    @Test
    void disabledUserCanNoLongerLogIn() throws Exception {
        mvc.perform(delete("/api/v1/auth/users/" + analyst.getId()).with(as(admin, "ADMIN")))
                .andExpect(status().isNoContent());

        mvc.perform(post("/api/v1/auth/login").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"analyste1\",\"password\":\"correct-horse\"}"))
                .andExpect(status().isUnauthorized());
    }

    private static JwtRequestPostProcessor as(User user, String role) {
        return jwt().jwt(token -> token.subject(user.getId().toString()))
                .authorities(new SimpleGrantedAuthority("ROLE_" + role));
    }
}
