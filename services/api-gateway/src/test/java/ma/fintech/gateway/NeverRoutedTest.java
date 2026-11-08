package ma.fintech.gateway;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * Paths the gateway must never pass to a service, even with a valid ADMIN token
 * (contracts/gateway-routes.md, §3.4): {@code /internal/**} (service-to-service, D33/D34),
 * {@code /predict} (ml-service, called by risk-service only), the JWKS and other actuator endpoints.
 * e2e scenario 7 relies on {@code /predict} being a 404 from outside.
 *
 * <p>Every route points at one fake that records the paths it receives. The status alone is not
 * enough: the real check is that the fake received nothing.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Import(TestJwt.Decoder.class)
class NeverRoutedTest {

    private static final FakeDownstream ANY_SERVICE = new FakeDownstream("{}");
    private static final List<String> SERVICE_URIS = List.of("AUTH_URI", "CUSTOMER_URI",
            "TRANSACTION_URI", "RISK_URI", "NOTIFICATION_URI", "AUDIT_URI", "ML_URI");

    @LocalServerPort
    private int port;

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();
    private final String adminToken = TestJwt.token("ADMIN");
    private int requestsBefore;

    @DynamicPropertySource
    static void routeEverythingToFake(DynamicPropertyRegistry registry) {
        SERVICE_URIS.forEach(name -> registry.add(name, ANY_SERVICE::uri));
    }

    @BeforeEach
    void countRequestsSoFar() {
        requestsBefore = ANY_SERVICE.receivedPaths().size();
    }

    @AfterAll
    static void stopFake() {
        ANY_SERVICE.close();
    }

    @ParameterizedTest(name = "{0} {1}")
    @CsvSource({
            "POST, /internal/customers/lookup",
            "GET,  /internal/customers/42/risk-profile",
            "POST, /predict",
            "GET,  /.well-known/jwks.json",
            "GET,  /api/v1/internal/customers/lookup",
            "GET,  /actuator/env",
            "GET,  /actuator/configprops",
    })
    void notRoutedEvenWithAdminToken(String method, String path) throws Exception {
        HttpResponse<String> response = send(method, path);

        ProblemAssertions.assertProblem(response, 404, path);
        assertNothingReachedAService();
    }

    /**
     * {@code /api/v1/customers/../../internal/...} matches the customers route as text. Forwarded,
     * customer-service would normalize it to {@code /internal/...}. Spring Security's
     * StrictServerWebExchangeFirewall (on by default) rejects it with 400 before routing.
     */
    @ParameterizedTest
    @ValueSource(strings = {
            "/api/v1/customers/../../internal/customers/lookup",
            "/api/v1/customers/%2e%2e/%2e%2e/internal/customers/lookup",
            "/api/v1/customers/..%2f..%2finternal/customers/lookup",
            "/api/v1/customers/%2F..%2F..%2Finternal/customers/lookup",
            "/api/v1/ml/..;/..;/predict",
    })
    void pathTraversalIsRejectedBeforeRouting(String path) throws Exception {
        HttpResponse<String> response = send("POST", path);

        assertEquals(400, response.statusCode(), path);
        assertNothingReachedAService();
    }

    /** Control case: a normal protected route does reach the fake, so the check above means something. */
    @Test
    void normalRouteDoesReachTheService() throws Exception {
        HttpResponse<String> response = send("GET", "/api/v1/customers");

        assertEquals(200, response.statusCode());
        assertEquals(List.of("/api/v1/customers"),
                ANY_SERVICE.receivedPaths().subList(requestsBefore, ANY_SERVICE.receivedPaths().size()));
    }

    private void assertNothingReachedAService() {
        List<String> received = ANY_SERVICE.receivedPaths();
        assertEquals(List.of(), received.subList(requestsBefore, received.size()),
                "requests that reached a service");
    }

    private HttpResponse<String> send(String method, String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:" + port + path))
                .header("Authorization", "Bearer " + adminToken)
                .header("Content-Type", "application/json")
                .timeout(Duration.ofSeconds(10))
                .method(method, method.equals("POST")
                        ? HttpRequest.BodyPublishers.ofString("{}")
                        : HttpRequest.BodyPublishers.noBody())
                .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }
}
