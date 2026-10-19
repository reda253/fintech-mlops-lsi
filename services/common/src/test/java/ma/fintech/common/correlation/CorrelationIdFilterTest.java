package ma.fintech.common.correlation;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import static org.assertj.core.api.Assertions.assertThat;

class CorrelationIdFilterTest {

    private static final String VALID = "3f1c2b4a-9d8e-4f00-a1b2-c3d4e5f60718";

    private final CorrelationIdFilter filter = new CorrelationIdFilter();
    private final MockHttpServletResponse response = new MockHttpServletResponse();
    private final AtomicReference<String> seenInMdc = new AtomicReference<>();

    @Test
    void reusesIncomingValidId() throws Exception {
        run(requestWithHeader(VALID));

        assertThat(seenInMdc.get()).isEqualTo(VALID);
        assertThat(response.getHeader(CorrelationId.HEADER)).isEqualTo(VALID);
    }

    @Test
    void generatesUuidWhenHeaderIsAbsent() throws Exception {
        run(new MockHttpServletRequest());

        assertThat(seenInMdc.get()).matches(CorrelationId.UUID_PATTERN);
        assertThat(response.getHeader(CorrelationId.HEADER)).isEqualTo(seenInMdc.get());
    }

    @Test
    void replacesInvalidIdSoNothingUntrustedReachesTheLogs() throws Exception {
        run(requestWithHeader("abc\n{\"level\":\"ERROR\"}"));

        assertThat(seenInMdc.get()).matches(CorrelationId.UUID_PATTERN);
    }

    @Test
    void clearsMdcAfterTheRequest() throws Exception {
        run(requestWithHeader(VALID));

        assertThat(MDC.get(CorrelationId.MDC_KEY)).isNull();
    }

    private void run(MockHttpServletRequest request) throws Exception {
        filter.doFilter(request, response, (req, res) -> seenInMdc.set(MDC.get(CorrelationId.MDC_KEY)));
    }

    private static MockHttpServletRequest requestWithHeader(String value) {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader(CorrelationId.HEADER, value);
        return request;
    }
}
