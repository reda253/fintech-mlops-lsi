package ma.fintech.auth.repository;

import java.util.Set;

import ma.fintech.auth.TestcontainersConfig;
import ma.fintech.auth.domain.User;
import ma.fintech.auth.domain.User.Role;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * Runs the real Flyway migrations on PostgreSQL, so the context only starts if the entity matches
 * V1 ({@code ddl-auto: validate}).
 */
@DataJpaTest
@Import(TestcontainersConfig.class)
class UserRepositoryTest {

    @Autowired
    UserRepository users;

    @Test
    void savesAndFindsByUsernameWithRolesArray() {
        users.saveAndFlush(new User("analyst1", "$2a$10$hash", Set.of(Role.ANALYSTE, Role.ADMIN)));

        User found = users.findByUsername("analyst1").orElseThrow();

        assertThat(found.getId()).isNotNull();
        assertThat(found.getRoles()).containsExactlyInAnyOrder(Role.ANALYSTE, Role.ADMIN);
        assertThat(found.isEnabled()).isTrue();
        assertThat(found.getCreatedAt()).isNotNull();
        assertThat(users.findByUsername("nobody")).isEmpty();
    }

    @Test
    void v2SeedsOneDemoAccountPerRole() {
        assertThat(users.findByUsername("admin").orElseThrow().getRoles()).containsExactly(Role.ADMIN);
        assertThat(users.findByUsername("analyste1").orElseThrow().getRoles()).containsExactly(Role.ANALYSTE);
        assertThat(users.findByUsername("simulateur1").orElseThrow().getRoles()).containsExactly(Role.SIMULATEUR);
    }

    @Test
    void usernameIsUnique() {
        users.saveAndFlush(new User("dup", "$2a$10$hash", Set.of(Role.SIMULATEUR)));

        User duplicate = new User("dup", "$2a$10$other", Set.of(Role.ADMIN));
        assertThatThrownBy(() -> users.saveAndFlush(duplicate))
                .isInstanceOf(DataIntegrityViolationException.class);
    }
}
