package ma.fintech.gateway;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;

import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpServer;

/**
 * Stand-in for a downstream service: a JDK HttpServer on a free port that answers every request
 * with 200 and a fixed JSON body, and remembers the headers of the last request it received.
 */
final class FakeDownstream implements AutoCloseable {

    private final HttpServer server;
    private final String body;
    private final AtomicReference<Headers> lastRequestHeaders = new AtomicReference<>();

    FakeDownstream(String body) {
        this.body = body;
        try {
            server = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
        } catch (IOException e) {
            throw new IllegalStateException("cannot start fake downstream", e);
        }
        server.createContext("/", exchange -> {
            lastRequestHeaders.set(exchange.getRequestHeaders());
            byte[] bytes = this.body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });
        server.start();
    }

    String uri() {
        return "http://localhost:" + server.getAddress().getPort();
    }

    String body() {
        return body;
    }

    /** Value of a header on the last request that reached this server, or null. */
    String lastRequestHeader(String name) {
        Headers headers = lastRequestHeaders.get();
        return headers == null ? null : headers.getFirst(name);
    }

    @Override
    public void close() {
        server.stop(0);
    }
}
