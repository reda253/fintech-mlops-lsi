package ma.fintech.common.correlation;

import java.io.IOException;

import org.springframework.http.HttpRequest;
import org.springframework.http.client.ClientHttpRequestExecution;
import org.springframework.http.client.ClientHttpRequestInterceptor;
import org.springframework.http.client.ClientHttpResponse;

/** Propagates the current correlation id on outgoing calls (transaction → risk → customer, ml-service). */
public class CorrelationIdInterceptor implements ClientHttpRequestInterceptor {

    @Override
    public ClientHttpResponse intercept(HttpRequest request, byte[] body, ClientHttpRequestExecution execution)
            throws IOException {
        CorrelationId.current().ifPresent(id -> request.getHeaders().set(CorrelationId.HEADER, id));
        return execution.execute(request, body);
    }
}
