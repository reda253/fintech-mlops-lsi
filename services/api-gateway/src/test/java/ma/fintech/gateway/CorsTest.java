package ma.fintech.gateway;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * CORS at the gateway (contracts/gateway-routes.md): the React app's origins only, applied before
 * authentication because a browser never sends the Authorization header on a preflight.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CorsTest {

    @LocalServerPort
    private int port;

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    @ParameterizedTest
    @ValueSource(strings = {"https://fintech.local", "http://localhost:5173"})
    void preflightFromFrontendIsAllowedWithoutToken(String origin) throws Exception {
        HttpResponse<String> response = send(preflight(origin, "POST"));

        assertEquals(200, response.statusCode());
        assertEquals(origin, header(response, "Access-Control-Allow-Origin"));
        assertTrue(header(response, "Access-Control-Allow-Methods").contains("POST"));
        String allowedHeaders = header(response, "Access-Control-Allow-Headers").toLowerCase();
        assertTrue(allowedHeaders.contains("authorization"), allowedHeaders);
        assertTrue(allowedHeaders.contains("content-type"), allowedHeaders);
        // Bearer tokens only, no cookies: credentials are never allowed cross-origin.
        assertFalse(response.headers().firstValue("Access-Control-Allow-Credentials").isPresent());
    }

    @Test
    void preflightFromUnknownOriginIsRejected() throws Exception {
        HttpResponse<String> response = send(preflight("https://evil.example", "POST"));

        assertEquals(403, response.statusCode());
        assertFalse(response.headers().firstValue("Access-Control-Allow-Origin").isPresent());
    }

    /**
     * The browser hides any cross-origin response, even a 401, unless it carries Allow-Origin.
     * Exposed headers let the app read the correlation id and the Location of a created resource.
     */
    @Test
    void actualResponseCarriesCorsHeadersEvenWhenRejected() throws Exception {
        HttpRequest request = base("/api/v1/customers")
                .header("Origin", "http://localhost:5173")
                .GET()
                .build();

        HttpResponse<String> response = send(request);

        assertEquals(401, response.statusCode());
        assertEquals("http://localhost:5173", header(response, "Access-Control-Allow-Origin"));
        String exposed = header(response, "Access-Control-Expose-Headers").toLowerCase();
        assertTrue(exposed.contains("x-correlation-id"), exposed);
        assertTrue(exposed.contains("location"), exposed);
    }

    private HttpRequest preflight(String origin, String method) {
        return base("/api/v1/customers")
                .header("Origin", origin)
                .header("Access-Control-Request-Method", method)
                .header("Access-Control-Request-Headers", "authorization,content-type")
                .method("OPTIONS", HttpRequest.BodyPublishers.noBody())
                .build();
    }

    private HttpRequest.Builder base(String path) {
        return HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:" + port + path))
                .timeout(Duration.ofSeconds(10));
    }

    private static String header(HttpResponse<?> response, String name) {
        return response.headers().firstValue(name).orElse("");
    }

    private HttpResponse<String> send(HttpRequest request) throws Exception {
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }
}
