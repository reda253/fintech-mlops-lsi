package ma.fintech.common.messaging;

import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** {@link IdempotentConsumer} for every AMQP service with a database. Unused beans cost nothing. */
@AutoConfiguration(afterName = {
        "org.springframework.boot.jdbc.autoconfigure.JdbcClientAutoConfiguration",
        "org.springframework.boot.jdbc.autoconfigure.DataSourceTransactionManagerAutoConfiguration",
        "org.springframework.boot.hibernate.autoconfigure.HibernateJpaAutoConfiguration"})
@ConditionalOnClass({RabbitTemplate.class, JdbcClient.class})
@ConditionalOnBean({JdbcClient.class, PlatformTransactionManager.class})
public class IdempotentConsumerAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    IdempotentConsumer idempotentConsumer(JdbcClient jdbc, PlatformTransactionManager transactionManager) {
        return new IdempotentConsumer(jdbc, new TransactionTemplate(transactionManager));
    }
}
