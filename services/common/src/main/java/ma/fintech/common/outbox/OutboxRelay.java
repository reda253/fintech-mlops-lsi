package ma.fintech.common.outbox;

import java.nio.charset.StandardCharsets;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import ma.fintech.common.correlation.CorrelationId;
import ma.fintech.common.events.Topology;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.AmqpException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.transaction.support.TransactionTemplate;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * Publishes committed outbox rows to {@code fintech.events} (§3.5). Every replica runs it:
 * {@code FOR UPDATE SKIP LOCKED} hands each row to one replica at a time. A row is marked published
 * only after the broker confirms it, so a crash between publish and mark re-sends it (at-least-once;
 * consumers are idempotent). On the first failure the batch stops, which keeps the order and avoids
 * hammering a broker that is down; the rows wait and {@code outbox_pending} rises.
 */
public class OutboxRelay {

    private static final Logger log = LoggerFactory.getLogger(OutboxRelay.class);

    private final JdbcClient jdbc;
    private final RabbitTemplate rabbit;
    private final TransactionTemplate transaction;
    private final JsonMapper jsonMapper;
    private final OutboxProperties properties;
    private final Counter failures;

    public OutboxRelay(JdbcClient jdbc, RabbitTemplate rabbit, TransactionTemplate transaction,
                       JsonMapper jsonMapper, OutboxProperties properties, MeterRegistry registry) {
        if (!rabbit.getConnectionFactory().isPublisherConfirms()) {
            throw new IllegalStateException(
                    "The outbox relay needs spring.rabbitmq.publisher-confirm-type=correlated");
        }
        this.jdbc = jdbc;
        this.rabbit = rabbit;
        this.transaction = transaction;
        this.jsonMapper = jsonMapper;
        this.properties = properties;
        if (registry != null) {
            Gauge.builder("outbox.pending", this, OutboxRelay::pendingOrNaN)
                    .description("Outbox events committed but not yet confirmed by RabbitMQ")
                    .register(registry);
            this.failures = Counter.builder("outbox.publish.failures")
                    .description("Relay publish attempts that failed or were not confirmed")
                    .register(registry);
        } else {
            this.failures = null;
        }
    }

    @Scheduled(fixedDelayString = "${fintech.outbox.relay-interval-ms:500}")
    public void relay() {
        Integer published = transaction.execute(status -> publishBatch());
        if (published != null && published > 0) {
            log.debug("Outbox relay published {} event(s)", published);
        }
    }

    /** Runs inside the transaction that holds the row locks. Returns how many rows were published. */
    private int publishBatch() {
        List<Row> rows = jdbc.sql("""
                        SELECT id, event_type, payload::text AS payload
                        FROM outbox_events
                        WHERE published_at IS NULL
                        ORDER BY created_at
                        LIMIT :limit
                        FOR UPDATE SKIP LOCKED""")
                .param("limit", properties.batchSize())
                .query((rs, n) -> new Row(rs.getObject("id", UUID.class), rs.getString("event_type"),
                        rs.getString("payload")))
                .list();
        int published = 0;
        for (Row row : rows) {
            try {
                send(row);
            } catch (Exception e) {
                if (e instanceof InterruptedException) {
                    Thread.currentThread().interrupt();
                }
                recordFailure(row, e);
                break;
            }
            jdbc.sql("UPDATE outbox_events SET published_at = :now WHERE id = :id")
                    .param("now", Timestamp.from(Instant.now()))
                    .param("id", row.id())
                    .update();
            published++;
        }
        return published;
    }

    private void send(Row row) throws Exception {
        MessageProperties props = new MessageProperties();
        props.setMessageId(row.id().toString());
        props.setType(row.type());
        props.setContentType(MessageProperties.CONTENT_TYPE_JSON);
        props.setContentEncoding(StandardCharsets.UTF_8.name());
        props.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
        JsonNode correlationId = jsonMapper.readTree(row.payload()).get("correlationId");
        if (correlationId != null && !correlationId.isNull()) {
            props.setHeader(CorrelationId.HEADER, correlationId.asString());
        }
        Message message = new Message(row.payload().getBytes(StandardCharsets.UTF_8), props);

        CorrelationData confirm = new CorrelationData(row.id().toString());
        rabbit.send(Topology.EVENTS_EXCHANGE, row.type(), message, confirm);
        CorrelationData.Confirm result = confirm.getFuture()
                .get(properties.confirmTimeout().toMillis(), TimeUnit.MILLISECONDS);
        if (!result.ack()) {
            throw new AmqpException("Broker refused the event (nack): " + result.reason());
        }
    }

    private void recordFailure(Row row, Exception e) {
        if (failures != null) {
            failures.increment();
        }
        String error = e.getClass().getSimpleName() + ": " + e.getMessage();
        log.warn("Outbox relay could not publish event {} ({}), will retry: {}", row.id(), row.type(), error);
        jdbc.sql("UPDATE outbox_events SET attempts = attempts + 1, last_error = :error WHERE id = :id")
                .param("error", error.length() > 1000 ? error.substring(0, 1000) : error)
                .param("id", row.id())
                .update();
    }

    /** Number of unpublished rows; served by the partial index ix_outbox_unpublished. */
    public long pending() {
        return jdbc.sql("SELECT count(*) FROM outbox_events WHERE published_at IS NULL")
                .query(Long.class)
                .single();
    }

    private double pendingOrNaN() {
        try {
            return pending();
        } catch (RuntimeException e) {
            return Double.NaN;    // database down: the Prometheus scrape must not fail
        }
    }

    private record Row(UUID id, String type, String payload) {
    }
}
