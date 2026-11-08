package ma.fintech.gateway;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.boot.micrometer.metrics.test.autoconfigure.AutoConfigureMetrics;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Which requests the gateway lets through without a token.
 * A {@link FakeDownstream} stands in for auth-service so we can see a public request actually reach it.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
// Tests disable metrics export by default, which removes /actuator/prometheus; turn it back on.
@AutoConfigureMetrics
class GatewaySecurityTest {

    private static final FakeDownstream FAKE_AUTH =
            new FakeDownstream("{\"accessToken\":\"a\",\"refreshToken\":\"r\"}");

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
    static void stopFakeAuth() {
        FAKE_AUTH.close();
    }

    @ParameterizedTest
    @ValueSource(strings = {"/actuator/health/liveness", "/actuator/health/readiness"})
    void probesAreAvailableWithoutAuthentication(String path) throws Exception {
        HttpResponse<String> response = send(get(path));
        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("\"status\":\"UP\""));
    }

    @ParameterizedTest
    @ValueSource(strings = {"/api/v1/auth/login", "/api/v1/auth/refresh"})
    void loginAndRefreshReachAuthServiceWithoutToken(String path) throws Exception {
        HttpResponse<String> response = send(postJson(path, "{\"username\":\"u\",\"password\":\"p\"}"));
        assertEquals(200, response.statusCode());
        assertEquals(FAKE_AUTH.body(), response.body());
    }

    @Test
    void getOnLoginIsNotPublic() throws Exception {
        assertUnauthorized(send(get("/api/v1/auth/login")));
    }

    @Test
    void otherAuthEndpointsRequireToken() throws Exception {
        assertUnauthorized(send(get("/api/v1/auth/me")));
        assertUnauthorized(send(postJson("/api/v1/auth/users", "{}")));
    }

    /** Prometheus scrapes without a token; Traefik never routes /actuator/** from outside. */
    @Test
    void prometheusScrapeIsAvailableWithoutAuthentication() throws Exception {
        HttpResponse<String> response = send(get("/actuator/prometheus"));
        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("application=\"api-gateway\""), "metrics tagged with the service name");
        assertUnauthorized(send(postJson("/actuator/prometheus", "{}")));
    }

    @ParameterizedTest
    @ValueSource(strings = {"/actuator/health", "/actuator/info", "/api/v1/customers"})
    void otherEndpointsStillRequireAuthentication(String path) throws Exception {
        assertUnauthorized(send(get(path)));
    }

    /** A token is present but unreadable: the resource-server entry point answers, not the default one. */
    @Test
    void malformedTokenGives401ProblemDetails() throws Exception {
        HttpResponse<String> response = send(request("/api/v1/customers")
                .header("Authorization", "Bearer not-a-jwt")
                .GET()
                .build());

        assertUnauthorized(response);
        assertTrue(response.headers().firstValue("WWW-Authenticate").orElse("")
                .contains("error=\"invalid_token\""));
    }

    private static void assertUnauthorized(HttpResponse<String> response) {
        ProblemAssertions.assertProblem(response, 401, response.uri().getPath());
        assertTrue(response.headers().firstValue("WWW-Authenticate").orElse("").startsWith("Bearer"));
    }

    private HttpRequest get(String path) {
        return request(path).GET().build();
    }

    private HttpRequest postJson(String path, String body) {
        return request(path)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();
    }

    private HttpRequest.Builder request(String path) {
        return HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:" + port + path))
                .timeout(Duration.ofSeconds(10));
    }

    private HttpResponse<String> send(HttpRequest request) throws Exception {
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }
}
