package ma.fintech.common.messaging;

import java.util.Map;

import org.springframework.boot.EnvironmentPostProcessor;
import org.springframework.boot.SpringApplication;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

/**
 * RabbitMQ delivery rules of contracts/events.md, as lowest-priority defaults (a service's
 * application.yml still wins):
 * <ul>
 *   <li>publisher confirms, which the outbox relay needs before marking a row published;</li>
 *   <li>ack only after the listener returns ({@code auto} = container acks on success);</li>
 *   <li>3 attempts in total (1 s, then 2 s), then reject without requeue, so the message goes to the
 *       queue's DLQ via {@code fintech.dlx}.</li>
 * </ul>
 * Harmless in services without AMQP: nothing reads these properties there.
 */
public class MessagingDefaultsEnvironmentPostProcessor implements EnvironmentPostProcessor, Ordered {

    static final Map<String, Object> DEFAULTS = Map.of(
            "spring.rabbitmq.publisher-confirm-type", "correlated",
            "spring.rabbitmq.listener.simple.acknowledge-mode", "auto",
            "spring.rabbitmq.listener.simple.default-requeue-rejected", "false",
            "spring.rabbitmq.listener.simple.retry.enabled", "true",
            "spring.rabbitmq.listener.simple.retry.max-retries", "2",
            "spring.rabbitmq.listener.simple.retry.initial-interval", "1s",
            "spring.rabbitmq.listener.simple.retry.multiplier", "2");

    @Override
    public void postProcessEnvironment(ConfigurableEnvironment environment, SpringApplication application) {
        environment.getPropertySources().addLast(new MapPropertySource("fintechMessagingDefaults", DEFAULTS));
    }

    /** After the config data processor, so application.yml is already in place and keeps priority. */
    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }
}
