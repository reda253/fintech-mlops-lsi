package ma.fintech.gateway;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * A service slower than the gateway's response timeout gets a 503 Problem Details (§3.6).
 * The timeout is lowered from 3 s to 500 ms here so the test stays fast; the behaviour is the same.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.cloud.gateway.server.webflux.httpclient.response-timeout=500ms")
class DownstreamTimeoutTest {

    private static final FakeDownstream SLOW_AUTH = new FakeDownstream("{}");

    @LocalServerPort
    private int port;

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    @DynamicPropertySource
    static void routeAuthToFake(DynamicPropertyRegistry registry) {
        registry.add("AUTH_URI", SLOW_AUTH::uri);
    }

    @AfterEach
    void fastAgain() {
        SLOW_AUTH.delay(Duration.ZERO);
    }

    @AfterAll
    static void stopFake() {
        SLOW_AUTH.close();
    }

    @Test
    void slowServiceGives503ProblemDetails() throws Exception {
        SLOW_AUTH.delay(Duration.ofMillis(1500));

        HttpResponse<String> response = login();

        ProblemAssertions.assertProblem(response, 503, "/api/v1/auth/login");
    }

    @Test
    void serviceWithinTimeoutIsProxied() throws Exception {
        SLOW_AUTH.delay(Duration.ofMillis(100));

        HttpResponse<String> response = login();

        assertEquals(200, response.statusCode());
        assertTrue(response.body().equals("{}"));
    }

    private HttpResponse<String> login() throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:" + port + "/api/v1/auth/login"))
                .header("Content-Type", "application/json")
                .timeout(Duration.ofSeconds(10))
                .POST(HttpRequest.BodyPublishers.ofString("{}"))
                .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }
}
