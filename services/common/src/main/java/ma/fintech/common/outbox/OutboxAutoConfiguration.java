package ma.fintech.common.outbox;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import tools.jackson.databind.json.JsonMapper;

/**
 * Transactional outbox (D15, D49). Opt-in with {@code fintech.outbox.enabled=true}: only producers
 * (auth, transaction, risk) have an {@code outbox_events} table.
 */
@AutoConfiguration(afterName = {
        "org.springframework.boot.amqp.autoconfigure.RabbitAutoConfiguration",
        "org.springframework.boot.jdbc.autoconfigure.JdbcClientAutoConfiguration",
        "org.springframework.boot.jackson.autoconfigure.JacksonAutoConfiguration"})
@ConditionalOnClass({RabbitTemplate.class, JdbcClient.class, JsonMapper.class, MeterRegistry.class})
@ConditionalOnProperty(prefix = "fintech.outbox", name = "enabled", havingValue = "true")
@EnableConfigurationProperties(OutboxProperties.class)
@EnableScheduling
public class OutboxAutoConfiguration {

    @Bean
    OutboxPublisher outboxPublisher(JdbcClient jdbc, JsonMapper jsonMapper,
                                    @Value("${spring.application.name}") String producer) {
        return new OutboxPublisher(jdbc, jsonMapper, producer);
    }

    @Bean
    OutboxRelay outboxRelay(JdbcClient jdbc, RabbitTemplate rabbit, PlatformTransactionManager transactionManager,
                            JsonMapper jsonMapper, OutboxProperties properties,
                            ObjectProvider<MeterRegistry> registry) {
        return new OutboxRelay(jdbc, rabbit, new TransactionTemplate(transactionManager), jsonMapper,
                properties, registry.getIfAvailable());
    }

    @Bean
    OutboxPurgeJob outboxPurgeJob(JdbcClient jdbc, OutboxProperties properties) {
        return new OutboxPurgeJob(jdbc, properties);
    }
}
