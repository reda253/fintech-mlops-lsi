package ma.fintech.common.eventing;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import ma.fintech.common.events.EventEnvelope;
import ma.fintech.common.events.Topology;
import ma.fintech.common.messaging.IdempotentConsumer;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.rabbitmq.RabbitMQContainer;

/**
 * A fake service with a database and a broker: the common outbox, topology and idempotent consumer
 * auto-configurations plus two listeners that exercise them.
 */
@SpringBootApplication
class EventingTestApplication {

    @Bean
    @ServiceConnection
    PostgreSQLContainer postgres() {
        return new PostgreSQLContainer("postgres:16-alpine");
    }

    @Bean
    @ServiceConnection
    RabbitMQContainer rabbit() {
        return new RabbitMQContainer("rabbitmq:4.3.6-management-alpine");
    }

    @Bean
    MeterRegistry meterRegistry() {
        return new SimpleMeterRegistry();
    }

    @Bean
    ReviewResultsListener reviewResultsListener(IdempotentConsumer idempotentConsumer) {
        return new ReviewResultsListener(idempotentConsumer);
    }

    @Bean
    FailingAlertsListener failingAlertsListener() {
        return new FailingAlertsListener();
    }

    /** Consumes through the idempotent helper; records each event it actually processed. */
    static class ReviewResultsListener {

        final List<EventEnvelope> processed = new CopyOnWriteArrayList<>();
        private final IdempotentConsumer idempotentConsumer;

        ReviewResultsListener(IdempotentConsumer idempotentConsumer) {
            this.idempotentConsumer = idempotentConsumer;
        }

        @RabbitListener(queues = Topology.TRANSACTION_REVIEW_RESULTS_QUEUE)
        void on(EventEnvelope event) {
            idempotentConsumer.handle(event, processed::add);
        }
    }

    /** Always fails, so every delivery ends in the DLQ after the retries. */
    static class FailingAlertsListener {

        final List<String> attempts = new CopyOnWriteArrayList<>();

        @RabbitListener(queues = Topology.NOTIFICATION_ALERTS_QUEUE)
        void on(EventEnvelope event) {
            attempts.add(event.eventId().toString());
            throw new IllegalStateException("simulated consumer failure");
        }
    }
}
