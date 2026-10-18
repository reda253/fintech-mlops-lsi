package ma.fintech.common.logging;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Configuration;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(OutputCaptureExtension.class)
class JsonLoggingEnvironmentPostProcessorTest {

    private static final String FORMAT = "logging.structured.format.console";

    private final JsonLoggingEnvironmentPostProcessor processor = new JsonLoggingEnvironmentPostProcessor();

    @Test
    void defaultsToEcsJson() {
        MockEnvironment env = new MockEnvironment();
        processor.postProcessEnvironment(env, new SpringApplication());

        assertThat(env.getProperty(FORMAT)).isEqualTo("ecs");
    }

    @Test
    void plainTextForLocalDevelopment() {
        MockEnvironment env = new MockEnvironment().withProperty("LOG_FORMAT", "plain");
        processor.postProcessEnvironment(env, new SpringApplication());

        assertThat(env.getProperty(FORMAT)).isNull();
    }

    @Test
    void serviceConfigurationWins() {
        MockEnvironment env = new MockEnvironment().withProperty(FORMAT, "logstash");
        processor.postProcessEnvironment(env, new SpringApplication());

        assertThat(env.getProperty(FORMAT)).isEqualTo("logstash");
    }

    @Test
    void everyLineIsJsonWithServiceNameAndCorrelationId(CapturedOutput output) {
        try (ConfigurableApplicationContext ignored = new SpringApplicationBuilder(Empty.class)
                .web(WebApplicationType.NONE)
                .properties("spring.application.name=risk-service")
                .run()) {
            MDC.put("correlationId", "3f1c2b4a-9d8e-4f00-a1b2-c3d4e5f60718");
            LoggerFactory.getLogger(getClass()).info("decision taken");
        } finally {
            MDC.clear();
        }

        String line = output.getOut().lines()
                .filter(l -> l.contains("decision taken")).findFirst().orElseThrow();
        assertThat(line).startsWith("{")
                .contains("\"correlationId\":\"3f1c2b4a-9d8e-4f00-a1b2-c3d4e5f60718\"")
                .contains("risk-service");
    }

    @Configuration(proxyBeanMethods = false)
    static class Empty {
    }
}
