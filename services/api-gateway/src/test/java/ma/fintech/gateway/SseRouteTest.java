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
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * GET /api/v1/notifications/stream is Server-Sent Events: one response that stays open, with an
 * event whenever a notification happens (contracts/gateway-routes.md). The gateway must not cut it
 * or buffer it.
 *
 * <p>The limits are scaled down so the test is short: response timeout 500 ms (3 s in prod) and
 * pool max lifetime 1 s (30 s in prod). The fake sends an event every 700 ms, so both limits are
 * crossed while the stream is open, as with real notifications minutes apart.
 *
 * <p>Spring Cloud Gateway's response timeout only covers the wait for the response headers. A
 * stream whose headers come late (no event to send yet) would get a 503 on the generic route,
 * so the stream route disables it.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {
        "spring.cloud.gateway.server.webflux.httpclient.response-timeout=500ms",
        "spring.cloud.gateway.server.webflux.httpclient.pool.max-life-time=1s"})
@Import(TestJwt.Decoder.class)
class SseRouteTest {

    private static final int EVENTS = 4;
    private static final Duration GAP = Duration.ofMillis(700);
    private static final HttpServer FAKE_NOTIFICATIONS = startEventStream();

    @LocalServerPort
    private int port;

    @DynamicPropertySource
    static void routeNotificationsToFake(DynamicPropertyRegistry registry) {
        registry.add("NOTIFICATION_URI", () -> "http://localhost:" + FAKE_NOTIFICATIONS.getAddress().getPort());
    }

    @AfterAll
    static void stopFake() {
        FAKE_NOTIFICATIONS.stop(0);
    }

    @Test
    void streamIsNeitherCutNorBuffered() throws Exception {
        assertStreamDelivered(openStream(""));
    }

    /** The service sends the headers only after 1 s, past the 500 ms response timeout. */
    @Test
    void streamWhoseHeadersComeLateIsNotCut() throws Exception {
        assertStreamDelivered(openStream("?slowStart"));
    }

    private record Received(HttpResponse<?> response, List<String> events, List<Long> arrivalMillis) {
    }

    private Received openStream(String query) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:" + port + "/api/v1/notifications/stream" + query))
                .header("Authorization", "Bearer " + TestJwt.token("ANALYSTE"))
                .header("Accept", "text/event-stream")
                .timeout(Duration.ofSeconds(15))
                .GET()
                .build();

        long start = System.nanoTime();
        HttpResponse<Stream<String>> response = HttpClient.newHttpClient()
                .send(request, HttpResponse.BodyHandlers.ofLines());
        List<String> events = new ArrayList<>();
        List<Long> arrivalMillis = new ArrayList<>();
        try (Stream<String> lines = response.body()) {
            lines.filter(line -> line.startsWith("data:")).forEach(line -> {
                events.add(line);
                arrivalMillis.add(Duration.ofNanos(System.nanoTime() - start).toMillis());
            });
        }
        return new Received(response, events, arrivalMillis);
    }

    private static void assertStreamDelivered(Received received) {
        HttpResponse<?> response = received.response();
        List<String> events = received.events();
        List<Long> arrivalMillis = received.arrivalMillis();
        assertEquals(200, response.statusCode());
        assertTrue(response.headers().firstValue("Content-Type").orElse("").startsWith("text/event-stream"));
        // Not cut: every event arrived, although the stream outlived both the timeout and the pool lifetime.
        assertEquals(List.of("data: 1", "data: 2", "data: 3", "data: 4"), events);
        // Not buffered: the first event arrived as soon as it was sent, not at the end of the stream.
        long firstToLast = arrivalMillis.get(EVENTS - 1) - arrivalMillis.get(0);
        assertTrue(firstToLast > 1800, "events spread over " + firstToLast + " ms, so they were buffered");
    }

    /** Fake notification-service: one event right away, then one every GAP, then end of stream. */
    private static HttpServer startEventStream() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
            server.createContext("/api/v1/notifications/stream", exchange -> {
                if ("slowStart".equals(exchange.getRequestURI().getQuery())) {
                    sleep(Duration.ofSeconds(1));
                }
                exchange.getResponseHeaders().add("Content-Type", "text/event-stream");
                exchange.sendResponseHeaders(200, 0); // 0 = chunked, length unknown
                try (OutputStream out = exchange.getResponseBody()) {
                    for (int i = 1; i <= EVENTS; i++) {
                        if (i > 1) {
                            sleep(GAP);
                        }
                        out.write(("data: " + i + "\n\n").getBytes(StandardCharsets.UTF_8));
                        out.flush();
                    }
                } catch (IOException e) {
                    // The gateway closed the connection: the assertions report it.
                }
            });
            server.start();
            return server;
        } catch (IOException e) {
            throw new IllegalStateException("cannot start fake notification-service", e);
        }
    }

    private static void sleep(Duration duration) {
        try {
            Thread.sleep(duration);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
