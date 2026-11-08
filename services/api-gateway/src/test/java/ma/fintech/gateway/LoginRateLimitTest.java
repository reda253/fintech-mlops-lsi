package ma.fintech.gateway;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Brute-force limit on POST /api/v1/auth/login only (contracts/gateway-routes.md, D42).
 * 3 attempts per hour here, so nothing refills during the test. Each test uses its own client IP,
 * sent the way Traefik sends it: appended as the last X-Forwarded-For entry.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {
        "gateway.rate-limit.login.capacity=3",
        "gateway.rate-limit.login.period=1h"})
class LoginRateLimitTest {

    private static final FakeDownstream FAKE_AUTH = new FakeDownstream("{}");

    @LocalServerPort
    private int port;

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    @DynamicPropertySource
    static void routeAuthToFake(DynamicPropertyRegistry registry) {
        registry.add("AUTH_URI", FAKE_AUTH::uri);
    }

    @AfterAll
    static void stopFake() {
        FAKE_AUTH.close();
    }

    @Test
    void fourthLoginFromSameIpGets429ProblemDetailsWithRetryAfter() throws Exception {
        for (int i = 0; i < 3; i++) {
            assertEquals(200, send(post("/api/v1/auth/login", "10.0.0.1")).statusCode());
        }

        HttpResponse<String> refused = send(post("/api/v1/auth/login", "10.0.0.1"));

        ProblemAssertions.assertProblem(refused, 429, "/api/v1/auth/login");
        long retryAfter = Long.parseLong(refused.headers().firstValue("Retry-After").orElseThrow());
        assertTrue(retryAfter > 0 && retryAfter <= 1200, "Retry-After = " + retryAfter); // 1 h / 3
    }

    @Test
    void otherIpsKeepTheirOwnLimit() throws Exception {
        for (int i = 0; i < 4; i++) {
            send(post("/api/v1/auth/login", "10.0.0.2"));
        }
        assertEquals(200, send(post("/api/v1/auth/login", "10.0.0.3")).statusCode());
    }

    /**
     * A client can write X-Forwarded-For itself; Traefik then appends the real IP. Only that last
     * entry counts, so changing the forged part does not give a fresh limit.
     */
    @Test
    void forgedForwardedForEntriesAreIgnored() throws Exception {
        for (int i = 0; i < 3; i++) {
            send(post("/api/v1/auth/login", randomIp() + ", 10.0.0.4"));
        }
        assertEquals(429, send(post("/api/v1/auth/login", randomIp() + ", 10.0.0.4")).statusCode());
    }

    @Test
    void refreshIsNotLimited() throws Exception {
        for (int i = 0; i < 5; i++) {
            assertEquals(200, send(post("/api/v1/auth/refresh", "10.0.0.5")).statusCode());
        }
    }

    /** The app must be able to read the 429 and its Retry-After from another origin. */
    @Test
    void refusalCarriesCorsHeaders() throws Exception {
        for (int i = 0; i < 3; i++) {
            send(post("/api/v1/auth/login", "10.0.0.6"));
        }
        HttpRequest request = base("/api/v1/auth/login", "10.0.0.6")
                .header("Origin", "http://localhost:5173")
                .POST(HttpRequest.BodyPublishers.ofString("{}"))
                .build();

        HttpResponse<String> refused = send(request);

        assertEquals(429, refused.statusCode());
        assertEquals("http://localhost:5173",
                refused.headers().firstValue("Access-Control-Allow-Origin").orElse(""));
    }

    private HttpRequest post(String path, String forwardedFor) {
        return base(path, forwardedFor).POST(HttpRequest.BodyPublishers.ofString("{}")).build();
    }

    private HttpRequest.Builder base(String path, String forwardedFor) {
        return HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:" + port + path))
                .header("Content-Type", "application/json")
                .header("X-Forwarded-For", forwardedFor)
                .timeout(Duration.ofSeconds(10));
    }

    private static String randomIp() {
        int n = UUID.randomUUID().hashCode();
        return "203.0." + (n >>> 8 & 0xff) + "." + (n & 0xff);
    }

    private HttpResponse<String> send(HttpRequest request) throws Exception {
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }
}
