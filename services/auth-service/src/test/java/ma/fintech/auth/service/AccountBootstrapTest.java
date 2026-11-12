package ma.fintech.auth.service;

import java.util.Optional;

import ma.fintech.auth.config.AccountsProperties;
import ma.fintech.auth.config.AccountsProperties.BootstrapAdmin;
import ma.fintech.auth.repository.UserRepository;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class AccountBootstrapTest {

    UserRepository users = mock(UserRepository.class);
    UserService userService = mock(UserService.class);

    AccountBootstrap bootstrap(boolean demoEnabled, String username, String password) {
        return new AccountBootstrap(
                new AccountsProperties(demoEnabled, new BootstrapAdmin(username, password)), users, userService);
    }

    @Test
    void localDefaultsChangeNothing() {
        assertThatCode(() -> bootstrap(true, "", "").run(null)).doesNotThrowAnyException();
        verifyNoInteractions(users, userService);
    }

    @Test
    void refusesToStartWithoutAnyAdmin() {
        when(users.findByUsername(anyString())).thenReturn(Optional.empty());
        when(users.countEnabledWithRole("ADMIN")).thenReturn(0L);

        assertThatThrownBy(() -> bootstrap(false, null, null).run(null))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("AUTH_BOOTSTRAP_ADMIN_USERNAME");
    }

    @Test
    void startsWithoutBootstrapWhenAnAdminAlreadyExists() {
        when(users.findByUsername(anyString())).thenReturn(Optional.empty());
        when(users.countEnabledWithRole("ADMIN")).thenReturn(1L);

        assertThatCode(() -> bootstrap(false, null, null).run(null)).doesNotThrowAnyException();
    }

    @Test
    void rejectsIncompleteShortOrDemoBootstrapAdmin() {
        assertThatThrownBy(() -> bootstrap(false, "reda", "").run(null))
                .hasMessageContaining("both a username and a password");
        assertThatThrownBy(() -> bootstrap(false, "", "long-enough-secret").run(null))
                .hasMessageContaining("both a username and a password");
        assertThatThrownBy(() -> bootstrap(false, "reda", "short").run(null))
                .hasMessageContaining("at least 12");
        assertThatThrownBy(() -> bootstrap(false, "admin", "long-enough-secret").run(null))
                .hasMessageContaining("demo username");
        // Rejected before touching the database.
        verify(userService, never()).create(anyString(), anyString(), any());
        verify(userService, never()).disable(any());
    }
}
