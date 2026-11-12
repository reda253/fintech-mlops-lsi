package ma.fintech.auth.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Account setup at startup (D47).
 *
 * @param demoEnabled    false on any shared environment: the V2 demo accounts have documented passwords
 * @param bootstrapAdmin first ADMIN, created only if absent; needed because creating users already requires an ADMIN
 */
@ConfigurationProperties("auth.accounts")
public record AccountsProperties(boolean demoEnabled, BootstrapAdmin bootstrapAdmin) {

    public AccountsProperties {
        bootstrapAdmin = bootstrapAdmin == null ? new BootstrapAdmin(null, null) : bootstrapAdmin;
    }

    /** Both values come from a Sealed Secret; both blank means "no bootstrap admin". */
    public record BootstrapAdmin(String username, String password) {

        public boolean configured() {
            return !isBlank(username) || !isBlank(password);
        }

        private static boolean isBlank(String value) {
            return value == null || value.isBlank();
        }
    }
}
