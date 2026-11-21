package ma.fintech.common.eventing;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import io.micrometer.core.instrument.MeterRegistry;
import ma.fintech.common.correlation.CorrelationId;
import ma.fintech.common.events.EventEnvelope;
import ma.fintech.common.events.EventTypes;
import ma.fintech.common.events.Topology;
import ma.fintech.common.messaging.IdempotentConsumer;
import ma.fintech.common.outbox.OutboxPublisher;
import ma.fintech.common.outbox.OutboxPurgeJob;
import ma.fintech.common.outbox.OutboxRelay;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.amqp.AmqpConnectException;
import org.springframework.amqp.core.AmqpAdmin;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.junit.jupiter.Testcontainers;
import tools.jackson.databind.json.JsonMapper;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.awaitility.Awaitility.await;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doCallRealMethod;
import static org.mockito.Mockito.doThrow;

/**
 * Outbox, relay, topology and idempotent consumer against a real PostgreSQL and RabbitMQ (§3.5).
 * The scheduled relay is slowed to once an hour so each test drives it by hand. Skipped where Docker
 * is unavailable (image builds run the tests inside docker build); the CI Java job runs it.
 */
@SpringBootTest(properties = {
        "spring.application.name=test-producer",
        "spring.main.web-application-type=none",
        "spring.sql.init.mode=always",
        "spring.sql.init.schema-locations=classpath:outbox-test-schema.sql",
        "fintech.outbox.enabled=true",
        "fintech.outbox.relay-interval-ms=3600000",
        "spring.rabbitmq.listener.simple.retry.initial-interval=100ms"})
@Testcontainers(disabledWithoutDocker = true)
class OutboxMessagingIntegrationTest {

    private static final String CORRELATION_ID = "3f1c2b4a-9d8e-4f00-a1b2-c3d4e5f60718";
    private static final Duration WAIT = Duration.ofSeconds(10);

    @Autowired
    OutboxPublisher outbox;
    @Autowired
    OutboxRelay relay;
    @Autowired
    OutboxPurgeJob purgeJob;
    @Autowired
    IdempotentConsumer idempotentConsumer;
    @Autowired
    JdbcClient jdbc;
    @Autowired
    AmqpAdmin admin;
    @Autowired
    JsonMapper jsonMapper;
    @Autowired
    MeterRegistry meters;
    @Autowired
    EventingTestApplication.ReviewResultsListener reviewResults;
    @Autowired
    EventingTestApplication.FailingAlertsListener failingAlerts;
    @MockitoSpyBean
    RabbitTemplate rabbit;

    TransactionTemplate transaction;

    @BeforeEach
    void clean(@Autowired PlatformTransactionManager transactionManager) {
        transaction = new TransactionTemplate(transactionManager);
        jdbc.sql("DELETE FROM outbox_events").update();
        jdbc.sql("DELETE FROM processed_events").update();
        jdbc.sql("DELETE FROM business_rows").update();
        for (String queue : List.of(Topology.AUDIT_QUEUE, Topology.dlq(Topology.NOTIFICATION_ALERTS_QUEUE))) {
            admin.purgeQueue(queue, false);
        }
        reviewResults.processed.clear();
        failingAlerts.attempts.clear();
    }

    @AfterEach
    void clearMdc() {
        MDC.clear();
    }

    /** A business change and its event in one transaction, like a real producer. */
    private UUID produce(String type) {
        return transaction.execute(status -> {
            UUID aggregate = UUID.randomUUID();
            jdbc.sql("INSERT INTO business_rows (id) VALUES (:id)").param("id", aggregate).update();
            return outbox.publish(type, aggregate.toString(), Map.of("username", "analyste1"), "analyste1");
        });
    }

    private long count(String sql) {
        return jdbc.sql(sql).query(Long.class).single();
    }

    private double pendingGauge() {
        return meters.get("outbox.pending").gauge().value();
    }

    @Nested
    class Publisher {

        @Test
        void committedTransactionKeepsTheChangeAndTheEvent() {
            UUID eventId = produce(EventTypes.LOGIN_SUCCEEDED);

            assertThat(count("SELECT count(*) FROM business_rows")).isEqualTo(1);
            assertThat(jdbc.sql("SELECT event_type FROM outbox_events WHERE id = :id").param("id", eventId)
                    .query(String.class).single()).isEqualTo(EventTypes.LOGIN_SUCCEEDED);
        }

        @Test
        void rolledBackTransactionLeavesNeitherTheChangeNorTheEvent() {
            assertThatThrownBy(() -> transaction.executeWithoutResult(status -> {
                jdbc.sql("INSERT INTO business_rows (id) VALUES (:id)").param("id", UUID.randomUUID()).update();
                outbox.publish(EventTypes.LOGIN_FAILED, "x", Map.of());
                throw new IllegalStateException("business failure after the event was written");
            })).isInstanceOf(IllegalStateException.class);

            assertThat(count("SELECT count(*) FROM business_rows")).isZero();
            assertThat(count("SELECT count(*) FROM outbox_events")).isZero();
        }

        @Test
        void publishingOutsideATransactionIsRefused() {
            assertThatThrownBy(() -> outbox.publish(EventTypes.LOGIN_FAILED, "x", Map.of()))
                    .isInstanceOf(IllegalTransactionStateException.class);
        }

        @Test
        void envelopeFollowsTheContract() throws Exception {
            MDC.put(CorrelationId.MDC_KEY, CORRELATION_ID);
            UUID eventId = produce(EventTypes.LOGIN_SUCCEEDED);

            String stored = jdbc.sql("SELECT payload::text FROM outbox_events WHERE id = :id")
                    .param("id", eventId).query(String.class).single();
            EventEnvelope envelope = jsonMapper.readValue(stored, EventEnvelope.class);
            assertThat(envelope.eventId()).isEqualTo(eventId);
            assertThat(envelope.type()).isEqualTo(EventTypes.LOGIN_SUCCEEDED);
            assertThat(envelope.version()).isEqualTo(1);
            assertThat(envelope.occurredAt()).isBefore(Instant.now().plusSeconds(1));
            assertThat(envelope.correlationId()).isEqualTo(CORRELATION_ID);
            assertThat(envelope.producer()).isEqualTo("test-producer");
            assertThat(envelope.actor()).isEqualTo("analyste1");
            assertThat(envelope.payload().get("username").asString()).isEqualTo("analyste1");
        }
    }

    @Nested
    class Relay {

        @Test
        void publishesWithTheContractPropertiesAndMarksTheRow() {
            MDC.put(CorrelationId.MDC_KEY, CORRELATION_ID);
            UUID eventId = produce(EventTypes.LOGIN_SUCCEEDED);

            relay.relay();

            Message message = rabbit.receive(Topology.AUDIT_QUEUE, WAIT.toMillis());
            assertThat(message).isNotNull();
            assertThat(message.getMessageProperties().getMessageId()).isEqualTo(eventId.toString());
            assertThat(message.getMessageProperties().getContentType()).isEqualTo("application/json");
            assertThat(message.getMessageProperties().getReceivedRoutingKey()).isEqualTo(EventTypes.LOGIN_SUCCEEDED);
            assertThat((String) message.getMessageProperties().getHeader(CorrelationId.HEADER)).isEqualTo(CORRELATION_ID);
            assertThat(message.getMessageProperties().getReceivedDeliveryMode()).isEqualTo(MessageDeliveryMode.PERSISTENT);
            assertThat(new String(message.getBody(), StandardCharsets.UTF_8)).contains(eventId.toString());
            assertThat(count("SELECT count(*) FROM outbox_events WHERE published_at IS NULL")).isZero();
            assertThat(pendingGauge()).isZero();
        }

        /**
         * The pod is killed after the commit and before any relay run: the row is all that survives.
         * The next relay run (another replica, or the same pod after restart) still publishes it.
         */
        @Test
        void eventCommittedBeforeACrashIsPublishedByTheNextRun() {
            UUID eventId = produce(EventTypes.LOGIN_FAILED);
            assertThat(pendingGauge()).isEqualTo(1);
            assertThat(rabbit.receive(Topology.AUDIT_QUEUE, 200)).isNull();

            relay.relay();

            Message message = rabbit.receive(Topology.AUDIT_QUEUE, WAIT.toMillis());
            assertThat(message.getMessageProperties().getMessageId()).isEqualTo(eventId.toString());
            assertThat(pendingGauge()).isZero();
        }

        @Test
        void failedPublishIsRecordedAndRetriedOnTheNextRun() {
            doThrow(new AmqpConnectException(new java.net.ConnectException("broker down")))
                    .doCallRealMethod()
                    .when(rabbit).send(anyString(), anyString(), any(Message.class), any(CorrelationData.class));
            UUID first = produce(EventTypes.LOGIN_SUCCEEDED);
            produce(EventTypes.LOGIN_SUCCEEDED);

            relay.relay();

            assertThat(jdbc.sql("SELECT attempts FROM outbox_events WHERE id = :id").param("id", first)
                    .query(Integer.class).single()).isEqualTo(1);
            assertThat(jdbc.sql("SELECT last_error FROM outbox_events WHERE id = :id").param("id", first)
                    .query(String.class).single()).contains("broker down");
            assertThat(pendingGauge()).as("batch stops at the first failure, keeping the order").isEqualTo(2);
            assertThat(meters.get("outbox.publish.failures").counter().count()).isGreaterThanOrEqualTo(1);

            relay.relay();

            assertThat(pendingGauge()).isZero();
            assertThat(rabbit.receive(Topology.AUDIT_QUEUE, WAIT.toMillis())).isNotNull();
            assertThat(rabbit.receive(Topology.AUDIT_QUEUE, WAIT.toMillis())).isNotNull();
        }

        @Test
        void purgeDeletesOnlyRowsPublishedMoreThanSevenDaysAgo() {
            String insert = """
                    INSERT INTO outbox_events (id, event_type, aggregate_id, payload, published_at)
                    VALUES (:id, 'auth.login.failed', 'x', '{}', now() - CAST(:age AS interval))""";
            jdbc.sql(insert).param("id", UUID.randomUUID()).param("age", "8 days").update();
            jdbc.sql(insert).param("id", UUID.randomUUID()).param("age", "6 days").update();
            jdbc.sql("""
                    INSERT INTO outbox_events (id, event_type, aggregate_id, payload, created_at)
                    VALUES (:id, 'auth.login.failed', 'x', '{}', now() - interval '30 days')""")
                    .param("id", UUID.randomUUID()).update();

            purgeJob.purge();

            assertThat(count("SELECT count(*) FROM outbox_events")).isEqualTo(2);
            assertThat(count("SELECT count(*) FROM outbox_events WHERE published_at IS NULL")).isEqualTo(1);
        }
    }

    @Nested
    class Consumer {

        @Test
        void relayedEventReachesTheListenerOnceEvenWhenPublishedTwice() {
            UUID eventId = produce(EventTypes.REVIEW_COMPLETED);
            relay.relay();
            await().atMost(WAIT).until(() -> reviewResults.processed.size() == 1);
            assertThat(reviewResults.processed.getFirst().eventId()).isEqualTo(eventId);

            // Relay crashed after the publish but before marking the row: the same event goes out again.
            jdbc.sql("UPDATE outbox_events SET published_at = NULL WHERE id = :id").param("id", eventId).update();
            relay.relay();

            await().pollDelay(Duration.ofSeconds(1)).atMost(WAIT)
                    .until(() -> admin.getQueueInfo(Topology.TRANSACTION_REVIEW_RESULTS_QUEUE).getMessageCount() == 0);
            assertThat(reviewResults.processed).hasSize(1);
            assertThat(count("SELECT count(*) FROM processed_events")).isEqualTo(1);
        }

        @Test
        void duplicateIsSkippedAndFailureLeavesNoMarker() {
            EventEnvelope event = new EventEnvelope(UUID.randomUUID(), EventTypes.REVIEW_COMPLETED, 1,
                    Instant.now(), CORRELATION_ID, "risk-service", "analyste1", jsonMapper.createObjectNode());

            assertThatThrownBy(() -> idempotentConsumer.handle(event, e -> {
                throw new IllegalStateException("database constraint");
            })).isInstanceOf(IllegalStateException.class);
            assertThat(count("SELECT count(*) FROM processed_events")).as("rolled back with the action").isZero();

            assertThat(idempotentConsumer.handle(event, e -> { })).isTrue();
            assertThat(idempotentConsumer.handle(event, e -> { })).isFalse();
            assertThat(count("SELECT count(*) FROM processed_events")).isEqualTo(1);
        }

        @Test
        void failingMessageGoesToItsDlqAfterThreeAttempts() {
            UUID eventId = produce(EventTypes.TRANSACTION_BLOCKED);

            relay.relay();

            Message dead = rabbit.receive(Topology.dlq(Topology.NOTIFICATION_ALERTS_QUEUE), WAIT.toMillis());
            assertThat(dead).isNotNull();
            assertThat(dead.getMessageProperties().getMessageId()).isEqualTo(eventId.toString());
            assertThat(failingAlerts.attempts).hasSize(3);
        }
    }

    @Test
    void wholeTopologyIsDeclared() {
        for (String queue : List.of(Topology.AUDIT_QUEUE, Topology.NOTIFICATION_ALERTS_QUEUE,
                Topology.TRANSACTION_REVIEW_RESULTS_QUEUE)) {
            assertThat(admin.getQueueInfo(queue)).as(queue).isNotNull();
            assertThat(admin.getQueueInfo(Topology.dlq(queue))).as(Topology.dlq(queue)).isNotNull();
        }
    }
}
