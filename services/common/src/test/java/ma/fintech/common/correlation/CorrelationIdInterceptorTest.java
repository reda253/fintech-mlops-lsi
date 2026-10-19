package ma.fintech.common.correlation;

import java.util.UUID;

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
        String id = UUID.randomUUID().toString();
        MDC.put(CorrelationId.MDC_KEY, id);
        server.expect(header(CorrelationId.HEADER, id))
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
