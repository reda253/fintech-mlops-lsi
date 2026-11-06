package ma.fintech.gateway;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Which requests the gateway lets through without a token.
 * A JDK HttpServer stands in for auth-service so we can see a public request actually reach it.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GatewaySecurityTest {

    private static final String TOKENS = "{\"accessToken\":\"a\",\"refreshToken\":\"r\"}";
    private static final HttpServer FAKE_AUTH = startFakeAuth();

    @LocalServerPort
    private int port;

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    @DynamicPropertySource
    static void routeAuthToFake(DynamicPropertyRegistry registry) {
        registry.add("AUTH_URI", () -> "http://localhost:" + FAKE_AUTH.getAddress().getPort());
    }

    @AfterAll
    static void stopFakeAuth() {
        FAKE_AUTH.stop(0);
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
        assertEquals(TOKENS, response.body());
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

    @ParameterizedTest
    @ValueSource(strings = {"/actuator/health", "/actuator/info",
            "/actuator/prometheus", "/api/v1/customers"})
    void otherEndpointsStillRequireAuthentication(String path) throws Exception {
        assertUnauthorized(send(get(path)));
    }

    private static void assertUnauthorized(HttpResponse<String> response) {
        assertEquals(401, response.statusCode());
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

    /** Answers any request under /api/v1/auth with a fixed token pair. */
    private static HttpServer startFakeAuth() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
            server.createContext("/api/v1/auth", exchange -> {
                byte[] body = TOKENS.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().add("Content-Type", "application/json");
                exchange.sendResponseHeaders(200, body.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(body);
                }
            });
            server.start();
            return server;
        } catch (IOException e) {
            throw new IllegalStateException("cannot start fake auth-service", e);
        }
    }
}
