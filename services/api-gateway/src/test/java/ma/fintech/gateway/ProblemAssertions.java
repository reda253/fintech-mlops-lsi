package ma.fintech.gateway;

import java.net.http.HttpResponse;

import ma.fintech.common.correlation.CorrelationId;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Checks a response against the ProblemDetail schema in contracts/common.yaml. */
final class ProblemAssertions {

    private ProblemAssertions() {
    }

    static void assertProblem(HttpResponse<String> response, int status, String instance) {
        assertEquals(status, response.statusCode());
        assertTrue(response.headers().firstValue("Content-Type").orElse("")
                .startsWith("application/problem+json"), "Content-Type");

        String body = response.body();
        String correlationId = response.headers().firstValue(CorrelationId.HEADER).orElseThrow();
        assertTrue(body.contains("\"status\":" + status), body);
        assertTrue(body.contains("\"title\":"), body);
        assertTrue(body.contains("\"instance\":\"" + instance + "\""), body);
        // Same id in the body as in the header, so a user can quote it from either.
        assertTrue(body.contains("\"correlationId\":\"" + correlationId + "\""), body);
    }
}
