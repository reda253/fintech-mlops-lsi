package ma.fintech.auth.service;

import ma.fintech.auth.TestcontainersConfig;
import ma.fintech.auth.domain.User;
import ma.fintech.auth.domain.User.Role;
import ma.fintech.auth.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.assertj.core.api.Assertions.assertThat;

/** Shared-environment settings (D47) on the real V1 + V2 migrations. */
@SpringBootTest(properties = {
        "auth.accounts.demo-enabled=false",
        "auth.accounts.bootstrap-admin.username=reda",
        "auth.accounts.bootstrap-admin.password=bootstrap-secret-42"
})
@Import(TestcontainersConfig.class)
class AccountBootstrapSharedEnvTest {

    @Autowired AccountBootstrap bootstrap;
    @Autowired UserRepository users;
    @Autowired UserService userService;
    @Autowired PasswordEncoder passwordEncoder;

    @Test
    void startupDisablesDemoAccountsCreatesTheAdminAndIsIdempotent() {
        for (String username : AccountBootstrap.DEMO_USERNAMES) {
            assertThat(users.findByUsername(username).orElseThrow().isEnabled()).as(username).isFalse();
        }
        User admin = users.findByUsername("reda").orElseThrow();
        assertThat(admin.isEnabled()).isTrue();
        assertThat(admin.getRoles()).containsExactly(Role.ADMIN);
        assertThat(passwordEncoder.matches("bootstrap-secret-42", admin.getPasswordHash())).isTrue();

        // Password changed later through the API: a restart must not reset it.
        userService.update(admin.getId(), "changed-through-api", null, null);
        bootstrap.run(null);

        User after = users.findByUsername("reda").orElseThrow();
        assertThat(passwordEncoder.matches("changed-through-api", after.getPasswordHash())).isTrue();
        assertThat(users.countEnabledWithRole(Role.ADMIN.name())).isEqualTo(1);
        assertThat(users.findByUsername("admin").orElseThrow().isEnabled()).isFalse();
    }
}
