package ma.fintech.auth.service;

import java.util.List;
import java.util.Set;

import ma.fintech.auth.config.AccountsProperties;
import ma.fintech.auth.config.AccountsProperties.BootstrapAdmin;
import ma.fintech.auth.domain.User;
import ma.fintech.auth.domain.User.Role;
import ma.fintech.auth.repository.UserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

/**
 * Makes the shared environment safe at startup (D47), before readiness turns UP:
 * <ol>
 *   <li>if demo accounts are off, disables the three V2 accounts (their passwords are public in the README);</li>
 *   <li>creates the bootstrap ADMIN if it does not exist yet (an existing account is never modified);</li>
 *   <li>refuses to start with demo accounts off and no enabled ADMIN, since nobody could create users.</li>
 * </ol>
 * Idempotent and safe with several replicas starting together: disabling is repeatable and a concurrent
 * create of the same admin hits the UNIQUE constraint, which is treated as "already created".
 */
@Component
public class AccountBootstrap implements ApplicationRunner {

    /** Seeded by {@code V2__seed_users.sql}. V2 is never edited: Flyway would reject the changed checksum. */
    static final List<String> DEMO_USERNAMES = List.of("admin", "analyste1", "simulateur1");
    static final int MIN_PASSWORD_LENGTH = 12;

    private static final Logger log = LoggerFactory.getLogger(AccountBootstrap.class);

    private final AccountsProperties properties;
    private final UserRepository users;
    private final UserService userService;

    public AccountBootstrap(AccountsProperties properties, UserRepository users, UserService userService) {
        this.properties = properties;
        this.users = users;
        this.userService = userService;
    }

    @Override
    public void run(ApplicationArguments args) {
        BootstrapAdmin admin = properties.bootstrapAdmin();
        if (admin.configured()) {
            validate(admin);
        }
        if (!properties.demoEnabled()) {
            disableDemoAccounts();
        }
        if (admin.configured()) {
            createAdminIfAbsent(admin);
        }
        if (!properties.demoEnabled() && users.countEnabledWithRole(Role.ADMIN.name()) == 0) {
            throw new IllegalStateException("Demo accounts are disabled and no enabled ADMIN exists: "
                    + "set AUTH_BOOTSTRAP_ADMIN_USERNAME and AUTH_BOOTSTRAP_ADMIN_PASSWORD");
        }
    }

    private void validate(BootstrapAdmin admin) {
        if (admin.username() == null || admin.username().isBlank()
                || admin.password() == null || admin.password().isBlank()) {
            throw new IllegalStateException("Bootstrap admin needs both a username and a password");
        }
        if (admin.password().length() < MIN_PASSWORD_LENGTH) {
            throw new IllegalStateException(
                    "Bootstrap admin password must have at least " + MIN_PASSWORD_LENGTH + " characters");
        }
        if (DEMO_USERNAMES.contains(admin.username())) {
            throw new IllegalStateException("Bootstrap admin cannot reuse a demo username: " + admin.username());
        }
    }

    private void disableDemoAccounts() {
        for (String username : DEMO_USERNAMES) {
            users.findByUsername(username)
                    .filter(User::isEnabled)
                    .ifPresent(user -> {
                        userService.disable(user.getId());     // also revokes its refresh tokens
                        log.info("Demo account disabled: {}", username);
                    });
        }
    }

    private void createAdminIfAbsent(BootstrapAdmin admin) {
        if (users.findByUsername(admin.username()).isPresent()) {
            return;     // never overwrite: the password may have been changed since through the API
        }
        try {
            userService.create(admin.username(), admin.password(), Set.of(Role.ADMIN));
            log.info("Bootstrap admin created: {}", admin.username());
        } catch (ResponseStatusException e) {
            log.info("Bootstrap admin already created by another replica: {}", admin.username());
        }
    }
}
