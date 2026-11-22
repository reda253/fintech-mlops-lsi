package ma.fintech.common.messaging;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class MessagingDefaultsEnvironmentPostProcessorTest {

    private final MessagingDefaultsEnvironmentPostProcessor processor = new MessagingDefaultsEnvironmentPostProcessor();

    @Test
    void appliesTheDeliveryRulesOfTheEventCatalog() {
        StandardEnvironment environment = new StandardEnvironment();

        processor.postProcessEnvironment(environment, null);

        assertThat(environment.getProperty("spring.rabbitmq.publisher-confirm-type")).isEqualTo("correlated");
        assertThat(environment.getProperty("spring.rabbitmq.listener.simple.default-requeue-rejected")).isEqualTo("false");
        // 1 delivery + 2 retries = the 3 attempts of contracts/events.md
        assertThat(environment.getProperty("spring.rabbitmq.listener.simple.retry.max-retries")).isEqualTo("2");
    }

    @Test
    void aServiceSettingStillWins() {
        StandardEnvironment environment = new StandardEnvironment();
        environment.getPropertySources().addFirst(new MapPropertySource("application",
                Map.of("spring.rabbitmq.listener.simple.retry.max-retries", "5")));

        processor.postProcessEnvironment(environment, null);

        assertThat(environment.getProperty("spring.rabbitmq.listener.simple.retry.max-retries")).isEqualTo("5");
    }
}
