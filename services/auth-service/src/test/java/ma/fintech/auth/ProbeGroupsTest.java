package ma.fintech.auth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.health.actuate.endpoint.HealthEndpointGroup;
import org.springframework.boot.health.actuate.endpoint.HealthEndpointGroups;
import org.springframework.boot.micrometer.metrics.test.autoconfigure.AutoConfigureMetrics;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.core.env.Environment;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Observability of a running Spring MVC service (§6.7, §6.8, §8.2, issue #14): probe groups, the
 * shutdown budget, and latency buckets in the real Prometheus output. The other MVC services check
 * the same settings in their application.yml (ProbeConfigTest).
 */
@SpringBootTest
@AutoConfigureMockMvc
// Tests disable metrics export by default, which removes /actuator/prometheus; turn it back on.
@AutoConfigureMetrics
@Import(TestcontainersConfig.class)
class ProbeGroupsTest {

    @Autowired
    HealthEndpointGroups groups;

    @Autowired
    Environment environment;

    @Autowired
    MockMvc mvc;

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

    /** K8s allows 30 s and preStop takes 5 s: Spring must finish in-flight requests before SIGKILL. */
    @Test
    void shutdownFinishesWithinTheKubernetesGracePeriod() {
        assertThat(environment.getProperty("server.shutdown")).isEqualTo("graceful");
        assertThat(environment.getProperty("spring.lifecycle.timeout-per-shutdown-phase")).isEqualTo("20s");
    }

    /** The SLO bounds (0.05 … 5 s) appear as buckets, so Grafana can compute p95 and the 2 s threshold. */
    @Test
    void scrapeHasLatencyBucketsOnTheObjectives() throws Exception {
        mvc.perform(get("/actuator/health/liveness")).andExpect(status().isOk());

        String scrape = mvc.perform(get("/actuator/prometheus"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        assertThat(scrape).contains("application=\"auth-service\"");
        for (String bound : new String[] {"0.05", "0.1", "0.25", "0.5", "1.0", "2.0", "5.0"}) {
            // Line by line: label values such as a uri template can contain braces.
            String le = "le=\"" + bound + "\"";
            assertThat(scrape.lines().anyMatch(line ->
                    line.startsWith("http_server_requests_seconds_bucket{") && line.contains(le)))
                    .as("bucket %s", le).isTrue();
        }
        assertThat(environment.getProperty("management.metrics.distribution.slo.http.client.requests"))
                .isEqualTo("50ms,100ms,250ms,500ms,1s,2s,5s");
    }
}
