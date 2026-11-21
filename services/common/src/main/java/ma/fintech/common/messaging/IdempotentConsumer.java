package ma.fintech.common.messaging;

import java.util.function.Consumer;

import ma.fintech.common.correlation.CorrelationId;
import ma.fintech.common.events.EventEnvelope;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * At-least-once delivery means the same event can arrive twice (relay crash before marking, broker
 * redelivery). {@link #handle} records the {@code eventId} in {@code processed_events} and runs the
 * action in the same transaction: a duplicate is skipped, and if the action throws, the insert rolls
 * back with it so the retry (then the DLQ) sees the event as new.
 *
 * <pre>{@code
 * @RabbitListener(queues = Topology.TRANSACTION_REVIEW_RESULTS_QUEUE)
 * void onReviewCompleted(EventEnvelope event) {
 *     idempotentConsumer.handle(event, e -> transactions.applyReview(e.payload()));
 * }
 * }</pre>
 */
public class IdempotentConsumer {

    private static final Logger log = LoggerFactory.getLogger(IdempotentConsumer.class);

    private final JdbcClient jdbc;
    private final TransactionTemplate transaction;

    public IdempotentConsumer(JdbcClient jdbc, TransactionTemplate transaction) {
        this.jdbc = jdbc;
        this.transaction = transaction;
    }

    /**
     * @return {@code true} if the action ran, {@code false} if the event had already been processed
     */
    public boolean handle(EventEnvelope event, Consumer<EventEnvelope> action) {
        String previous = MDC.get(CorrelationId.MDC_KEY);
        if (event.correlationId() != null) {
            // Same rule as the HTTP filter (D40): only a UUID reaches the logs.
            MDC.put(CorrelationId.MDC_KEY, CorrelationId.acceptOrGenerate(event.correlationId()));
        }
        try {
            return Boolean.TRUE.equals(transaction.execute(status -> {
                int inserted = jdbc.sql(
                                "INSERT INTO processed_events (event_id) VALUES (:id) ON CONFLICT (event_id) DO NOTHING")
                        .param("id", event.eventId())
                        .update();
                if (inserted == 0) {
                    log.info("Skipping duplicate event {} ({})", event.eventId(), event.type());
                    return false;
                }
                action.accept(event);
                return true;
            }));
        } finally {
            if (previous != null) {
                MDC.put(CorrelationId.MDC_KEY, previous);
            } else {
                MDC.remove(CorrelationId.MDC_KEY);
            }
        }
    }
}
