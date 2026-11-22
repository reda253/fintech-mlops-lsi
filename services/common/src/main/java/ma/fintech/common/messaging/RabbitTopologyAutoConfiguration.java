package ma.fintech.common.messaging;

import java.util.ArrayList;
import java.util.List;

import ma.fintech.common.events.EventTypes;
import ma.fintech.common.events.Topology;
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarable;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.FanoutExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.JacksonJsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import tools.jackson.databind.json.JsonMapper;

/**
 * The whole durable topology of contracts/events.md, declared by every service that has AMQP
 * (producers too, D49): a queue must exist before the first event is routed to it, otherwise the
 * topic exchange drops the event and the publisher confirm still says "ack". Declarations are
 * idempotent; RabbitAdmin runs them on every (re)connection. The per-replica live queue of
 * notification-service is not here: it is server-named and belongs to that service.
 */
@AutoConfiguration(afterName = "org.springframework.boot.jackson.autoconfigure.JacksonAutoConfiguration",
        beforeName = "org.springframework.boot.amqp.autoconfigure.RabbitAutoConfiguration")
@ConditionalOnClass({RabbitTemplate.class, JsonMapper.class})
public class RabbitTopologyAutoConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "fintech.messaging.topology", name = "enabled", matchIfMissing = true)
    Declarables fintechTopology() {
        TopicExchange events = new TopicExchange(Topology.EVENTS_EXCHANGE, true, false);
        DirectExchange deadLetters = new DirectExchange(Topology.DEAD_LETTER_EXCHANGE, true, false);
        List<Declarable> declarables = new ArrayList<>(List.of(events, deadLetters,
                new FanoutExchange(Topology.NOTIFICATIONS_LIVE_EXCHANGE, true, false)));

        Queue audit = queueWithDlq(Topology.AUDIT_QUEUE, deadLetters, declarables);
        declarables.add(BindingBuilder.bind(audit).to(events).with("#"));

        Queue alerts = queueWithDlq(Topology.NOTIFICATION_ALERTS_QUEUE, deadLetters, declarables);
        declarables.add(BindingBuilder.bind(alerts).to(events).with(EventTypes.TRANSACTION_REVIEW));
        declarables.add(BindingBuilder.bind(alerts).to(events).with(EventTypes.TRANSACTION_BLOCKED));

        Queue reviewResults = queueWithDlq(Topology.TRANSACTION_REVIEW_RESULTS_QUEUE, deadLetters, declarables);
        declarables.add(BindingBuilder.bind(reviewResults).to(events).with(EventTypes.REVIEW_COMPLETED));

        return new Declarables(declarables);
    }

    /** Durable queue whose rejected messages go to {@code fintech.dlx} with routing key = queue name. */
    private static Queue queueWithDlq(String name, DirectExchange deadLetters, List<Declarable> declarables) {
        Queue queue = QueueBuilder.durable(name)
                .deadLetterExchange(Topology.DEAD_LETTER_EXCHANGE)
                .deadLetterRoutingKey(name)
                .build();
        Queue dlq = QueueBuilder.durable(Topology.dlq(name)).build();
        Binding dlqBinding = BindingBuilder.bind(dlq).to(deadLetters).with(name);
        declarables.addAll(List.of(queue, dlq, dlqBinding));
        return queue;
    }

    /** Lets {@code @RabbitListener} methods take an {@code EventEnvelope} (or any record) directly. */
    @Bean
    @ConditionalOnMissingBean(MessageConverter.class)
    MessageConverter jacksonMessageConverter(ObjectProvider<JsonMapper> jsonMapper) {
        return new JacksonJsonMessageConverter(jsonMapper.getIfAvailable(JsonMapper::new));
    }
}
