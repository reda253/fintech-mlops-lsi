package ma.fintech.notification;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.env.YamlPropertySourceLoader;
import org.springframework.core.env.PropertySource;
import org.springframework.core.io.ClassPathResource;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Kubernetes probe groups (§6.7, CLAUDE.md "Health"): liveness never checks a dependency, readiness
 * checks the database only, never RabbitMQ. Reads this service's application.yml, so it needs no
 * database or Docker; auth-service's ProbeGroupsTest checks the same rule on a running context.
 */
class ProbeConfigTest {

    private static final String GROUPS = "management.endpoint.health.group.";

    @Test
    void livenessChecksNoDependency() throws Exception {
        assertThat(property(GROUPS + "liveness.include")).isEqualTo("livenessState");
    }

    @Test
    void readinessChecksTheDatabaseButNeverRabbit() throws Exception {
        assertThat(property(GROUPS + "readiness.include")).isEqualTo("readinessState,db");
    }

    @Test
    void probesAndGracefulShutdownAreOn() throws Exception {
        assertThat(property("management.endpoint.health.probes.enabled")).isEqualTo("true");
        assertThat(property("server.shutdown")).isEqualTo("graceful");
    }

    private static String property(String name) throws Exception {
        List<PropertySource<?>> sources = new YamlPropertySourceLoader()
                .load("application", new ClassPathResource("application.yml"));
        Object value = sources.getFirst().getProperty(name);
        return value == null ? null : value.toString();
    }
}
