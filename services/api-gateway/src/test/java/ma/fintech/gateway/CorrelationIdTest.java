package ma.fintech.gateway;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import ma.fintech.common.correlation.CorrelationId;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

/**
 * X-Correlation-Id at the edge (§3.10, contracts/gateway-routes.md): accept a valid UUID or generate
 * one, forward it downstream, and return it on every response, including those Spring Security rejects.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CorrelationIdTest {

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
    void generatesIdWhenAbsentAndSendsTheSameOneDownstreamAndBack() throws Exception {
        HttpResponse<String> response = send(login(null));

        String returned = response.headers().firstValue(CorrelationId.HEADER).orElseThrow();
        assertDoesNotThrow(() -> UUID.fromString(returned));
        assertEquals(returned, FAKE_AUTH.lastRequestHeader(CorrelationId.HEADER));
    }

    @Test
    void keepsValidIncomingId() throws Exception {
        String incoming = UUID.randomUUID().toString();

        HttpResponse<String> response = send(login(incoming));

        assertEquals(incoming, response.headers().firstValue(CorrelationId.HEADER).orElseThrow());
        assertEquals(incoming, FAKE_AUTH.lastRequestHeader(CorrelationId.HEADER));
    }

    /** The header ends up in every log line, so anything but a UUID is replaced (log injection). */
    @ParameterizedTest
    @ValueSource(strings = {"abc", "not-a-uuid-at-all", "0f0f0f0f-0000-0000-0000-00000000000 x"})
    void replacesInvalidIncomingId(String incoming) throws Exception {
        HttpResponse<String> response = send(login(incoming));

        String returned = response.headers().firstValue(CorrelationId.HEADER).orElseThrow();
        assertNotEquals(incoming, returned);
        assertDoesNotThrow(() -> UUID.fromString(returned));
        assertEquals(returned, FAKE_AUTH.lastRequestHeader(CorrelationId.HEADER));
    }

    @Test
    void rejectedRequestStillCarriesId() throws Exception {
        String incoming = UUID.randomUUID().toString();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:" + port + "/api/v1/customers"))
                .header(CorrelationId.HEADER, incoming)
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> response = send(request);

        assertEquals(401, response.statusCode());
        assertEquals(incoming, response.headers().firstValue(CorrelationId.HEADER).orElseThrow());
    }

    private HttpRequest login(String correlationId) {
        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:" + port + "/api/v1/auth/login"))
                .header("Content-Type", "application/json")
                .timeout(Duration.ofSeconds(10))
                .POST(HttpRequest.BodyPublishers.ofString("{}"));
        if (correlationId != null) {
            builder.header(CorrelationId.HEADER, correlationId);
        }
        return builder.build();
    }

    private HttpResponse<String> send(HttpRequest request) throws Exception {
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }
}
