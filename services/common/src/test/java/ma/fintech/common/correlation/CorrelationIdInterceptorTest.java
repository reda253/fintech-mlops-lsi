package ma.fintech.common.correlation;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.headerDoesNotExist;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class CorrelationIdInterceptorTest {

    private final RestClient.Builder builder = RestClient.builder()
            .requestInterceptor(new CorrelationIdInterceptor());
    private final MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
    private final RestClient client = builder.build();

    @AfterEach
    void clearMdc() {
        MDC.clear();
    }

    @Test
    void copiesCurrentIdOntoOutgoingCall() {
        MDC.put(CorrelationId.MDC_KEY, "3f1c2b4a-9d8e-4f00-a1b2-c3d4e5f60718");
        server.expect(header(CorrelationId.HEADER, "3f1c2b4a-9d8e-4f00-a1b2-c3d4e5f60718"))
                .andRespond(withSuccess());

        client.get().uri("http://risk/internal/x").retrieve().toBodilessEntity();

        server.verify();
    }

    @Test
    void sendsNothingOutsideARequest() {
        server.expect(headerDoesNotExist(CorrelationId.HEADER)).andRespond(withSuccess());

        client.get().uri("http://risk/internal/x").retrieve().toBodilessEntity();

        server.verify();
    }
}
