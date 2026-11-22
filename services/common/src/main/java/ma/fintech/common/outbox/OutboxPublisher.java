package ma.fintech.common.outbox;

import java.time.Instant;
import java.util.UUID;

import ma.fintech.common.correlation.CorrelationId;
import ma.fintech.common.events.EventEnvelope;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import tools.jackson.databind.json.JsonMapper;

/**
 * Writes an event into {@code outbox_events} in the caller's transaction (D15, §3.5). Nothing is sent
 * here: {@link OutboxRelay} publishes it after commit. If the business transaction rolls back, the
 * event disappears with it; if the pod dies after commit, the row is still there for the relay.
 */
public class OutboxPublisher {

    /** Actor for changes nobody typed in (automatic decisions, scheduled jobs). */
    public static final String SYSTEM_ACTOR = "system";

    private static final int VERSION = 1;

    private final JdbcClient jdbc;
    private final JsonMapper jsonMapper;
    private final String producer;

    public OutboxPublisher(JdbcClient jdbc, JsonMapper jsonMapper, String producer) {
        this.jdbc = jdbc;
        this.jsonMapper = jsonMapper;
        this.producer = producer;
    }

    /** Same as {@link #publish(String, String, Object, String)} with actor {@value #SYSTEM_ACTOR}. */
    public UUID publish(String type, String aggregateId, Object payload) {
        return publish(type, aggregateId, payload, SYSTEM_ACTOR);
    }

    /**
     * @param type        an {@code EventTypes} constant (= routing key)
     * @param aggregateId id of the changed entity (transaction, review, user), to debug the table
     * @param payload     any object Jackson can serialize; must never hold secrets
     * @param actor       username behind the change (stored by audit as {@code actor})
     * @return the new event id
     * @throws IllegalTransactionStateException if no transaction is active: an event written outside the
     *         business transaction would break the outbox guarantee
     */
    public UUID publish(String type, String aggregateId, Object payload, String actor) {
        if (!TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalTransactionStateException(
                    "OutboxPublisher.publish must run inside the business transaction (@Transactional)");
        }
        EventEnvelope envelope = new EventEnvelope(UUID.randomUUID(), type, VERSION, Instant.now(),
                CorrelationId.current().orElse(null), producer, actor, jsonMapper.valueToTree(payload));
        jdbc.sql("""
                        INSERT INTO outbox_events (id, event_type, aggregate_id, payload)
                        VALUES (:id, :type, :aggregateId, CAST(:payload AS jsonb))""")
                .param("id", envelope.eventId())
                .param("type", type)
                .param("aggregateId", aggregateId)
                .param("payload", jsonMapper.writeValueAsString(envelope))
                .update();
        return envelope.eventId();
    }
}
