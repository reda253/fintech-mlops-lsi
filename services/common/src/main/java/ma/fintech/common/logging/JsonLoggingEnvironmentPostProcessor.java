package ma.fintech.common.logging;

import java.util.Map;

import org.springframework.boot.EnvironmentPostProcessor;
import org.springframework.boot.SpringApplication;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

/**
 * JSON logs on stdout for every service (§3.10), so Loki can search them by {@code correlationId}
 * (D27). ECS format: each line carries {@code service.name} (= {@code spring.application.name}) and
 * every MDC entry. Added as the lowest-priority source, so a service's own
 * {@code logging.structured.format.console} still wins. {@code LOG_FORMAT=plain} gives readable
 * text for local runs.
 */
public class JsonLoggingEnvironmentPostProcessor implements EnvironmentPostProcessor, Ordered {

    static final String FORMAT_PROPERTY = "logging.structured.format.console";

    @Override
    public void postProcessEnvironment(ConfigurableEnvironment environment, SpringApplication application) {
        String format = environment.getProperty("LOG_FORMAT", "ecs");
        if (format.equalsIgnoreCase("plain")) {
            return;
        }
        environment.getPropertySources()
                .addLast(new MapPropertySource("fintechLoggingDefaults", Map.of(FORMAT_PROPERTY, format)));
    }

    /** After the config data processor, so application.yml is already in place when this adds its default. */
    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }
}
