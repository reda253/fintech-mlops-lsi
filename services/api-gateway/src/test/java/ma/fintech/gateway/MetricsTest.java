package ma.fintech.gateway;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.micrometer.metrics.test.autoconfigure.AutoConfigureMetrics;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.env.Environment;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Gateway observability (§6.8, §8.2, issue #14): latency buckets aligned on the objectives in the
 * real scrape output, and a shutdown budget that fits the Kubernetes grace period.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
// Tests disable metrics export by default, which removes /actuator/prometheus; turn it back on.
@AutoConfigureMetrics
class MetricsTest {

    @LocalServerPort
    private int port;

    @Autowired
    private Environment environment;

    private final HttpClient client = HttpClient.newHttpClient();

    /** The gateway's own server latency covers the whole proxied call, so its buckets drive the 2 s SLO. */
    @Test
    void scrapeHasLatencyBucketsOnTheObjectives() throws Exception {
        assertEquals(200, get("/actuator/health/liveness").statusCode());

        String scrape = scrapeOnceRecorded();

        assertTrue(scrape.contains("application=\"api-gateway\""), "application tag");
        for (String bound : new String[] {"0.05", "0.1", "0.25", "0.5", "1.0", "2.0", "5.0"}) {
            // Line by line: label values such as uri="/actuator/health/{*path}" contain braces.
            String le = "le=\"" + bound + "\"";
            assertTrue(scrape.lines().anyMatch(line ->
                    line.startsWith("http_server_requests_seconds_bucket{") && line.contains(le)), "bucket " + le);
        }
    }

    /** K8s allows 30 s and preStop takes 5 s: in-flight requests must finish before SIGKILL. */
    @Test
    void shutdownFinishesWithinTheKubernetesGracePeriod() {
        assertEquals("graceful", environment.getProperty("server.shutdown"));
        assertEquals("20s", environment.getProperty("spring.lifecycle.timeout-per-shutdown-phase"));
    }

    /**
     * WebFlux records a request's timer just after the response is sent, so a scrape made right
     * after can miss it. Poll briefly until the completed-request histogram is there.
     */
    private String scrapeOnceRecorded() throws Exception {
        String scrape = "";
        for (int attempt = 0; attempt < 50; attempt++) {
            scrape = get("/actuator/prometheus").body();
            if (scrape.contains("http_server_requests_seconds_bucket")) {
                return scrape;
            }
            Thread.sleep(100);
        }
        return scrape;
    }

    private HttpResponse<String> get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:" + port + path))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }
}
