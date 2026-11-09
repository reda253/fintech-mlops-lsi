package ma.fintech.transaction;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.env.YamlPropertySourceLoader;
import org.springframework.core.env.PropertySource;
import org.springframework.core.io.ClassPathResource;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Observability settings (§6.7, §6.8, §8.2, issue #14), read from this service's application.yml so
 * the test needs no database or Docker. auth-service and api-gateway check the same rules on a
 * running application, including the buckets in the real Prometheus output.
 */
class ProbeConfigTest {

    private static final String GROUPS = "management.endpoint.health.group.";
    private static final String BUCKETS = "50ms,100ms,250ms,500ms,1s,2s,5s";

    /** Liveness never checks a dependency: a database outage must not restart every pod. */
    @Test
    void livenessChecksNoDependency() throws Exception {
        assertThat(property(GROUPS + "liveness.include")).isEqualTo("livenessState");
    }

    /** Readiness checks the database only; never RabbitMQ (the outbox buffers) nor ml-service. */
    @Test
    void readinessChecksTheDatabaseOnly() throws Exception {
        assertThat(property(GROUPS + "readiness.include")).isEqualTo("readinessState,db");
    }

    @Test
    void probesAndGracefulShutdownAreOn() throws Exception {
        assertThat(property("management.endpoint.health.probes.enabled")).isEqualTo("true");
        assertThat(property("server.shutdown")).isEqualTo("graceful");
    }

    /** K8s allows 30 s and preStop takes 5 s: Spring must finish in-flight requests before SIGKILL. */
    @Test
    void shutdownFinishesWithinTheKubernetesGracePeriod() throws Exception {
        assertThat(property("spring.lifecycle.timeout-per-shutdown-phase")).isEqualTo("20s");
    }

    /** Incoming and outgoing calls both get latency buckets aligned on the objectives (2 s is one). */
    @Test
    void latencyHistogramsForServerAndClientCalls() throws Exception {
        for (String metric : List.of("http.server.requests", "http.client.requests")) {
            assertThat(property("management.metrics.distribution.percentiles-histogram." + metric))
                    .as(metric).isEqualTo("true");
            assertThat(property("management.metrics.distribution.slo." + metric)).as(metric).isEqualTo(BUCKETS);
        }
        assertThat(property("management.metrics.tags.application")).isEqualTo("${spring.application.name}");
    }

    private static String property(String name) throws Exception {
        List<PropertySource<?>> sources = new YamlPropertySourceLoader()
                .load("application", new ClassPathResource("application.yml"));
        Object value = sources.getFirst().getProperty(name);
        return value == null ? null : value.toString();
    }
}
