package ma.fintech.auth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.health.actuate.endpoint.HealthEndpointGroup;
import org.springframework.boot.health.actuate.endpoint.HealthEndpointGroups;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Kubernetes probe groups (§6.7, CLAUDE.md "Health"): liveness never checks a dependency, readiness
 * checks the database only, never RabbitMQ. Asked of the running application, not of the YAML.
 */
@SpringBootTest
@Import(TestcontainersConfig.class)
class ProbeGroupsTest {

    @Autowired
    HealthEndpointGroups groups;

    @Test
    void livenessChecksNoDependency() {
        HealthEndpointGroup liveness = groups.get("liveness");
        assertThat(liveness.isMember("livenessState")).isTrue();
        assertThat(liveness.isMember("db")).isFalse();
        assertThat(liveness.isMember("rabbit")).isFalse();
    }

    @Test
    void readinessChecksTheDatabaseButNeverRabbit() {
        HealthEndpointGroup readiness = groups.get("readiness");
        assertThat(readiness.isMember("readinessState")).isTrue();
        assertThat(readiness.isMember("db")).isTrue();
        assertThat(readiness.isMember("rabbit")).isFalse();
    }
}
