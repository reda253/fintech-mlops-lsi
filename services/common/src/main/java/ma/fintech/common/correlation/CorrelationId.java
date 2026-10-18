package ma.fintech.common.correlation;

import java.util.Optional;
import java.util.UUID;
import java.util.regex.Pattern;

import org.slf4j.MDC;

/** The {@code X-Correlation-Id} header (§3.10) and its MDC key, shared by filters, clients, logs and events. */
public final class CorrelationId {

    public static final String HEADER = "X-Correlation-Id";

    /** Key in the MDC, and so the field name in every JSON log line (Loki searches on it). */
    public static final String MDC_KEY = "correlationId";

    /** Canonical lower- or upper-case UUID, as declared in contracts/common.yaml. */
    public static final String UUID_PATTERN =
            "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";

    private static final Pattern VALID = Pattern.compile(UUID_PATTERN);

    private CorrelationId() {
    }

    /** The id of the request being handled on this thread, if any. */
    public static Optional<String> current() {
        return Optional.ofNullable(MDC.get(MDC_KEY));
    }

    /**
     * Returns the incoming value when it is a UUID, otherwise a new one. The header comes from the
     * client and ends up in every log line, so anything else is dropped (log injection).
     */
    static String acceptOrGenerate(String incoming) {
        return incoming != null && VALID.matcher(incoming).matches()
                ? incoming
                : UUID.randomUUID().toString();
    }
}
