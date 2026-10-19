package ma.fintech.common.correlation;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.restclient.RestClientCustomizer;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@AutoConfiguration
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
public class CorrelationAutoConfiguration {

    @Bean
    FilterRegistrationBean<CorrelationIdFilter> correlationIdFilter() {
        FilterRegistrationBean<CorrelationIdFilter> registration = new FilterRegistrationBean<>(new CorrelationIdFilter());
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE);
        return registration;
    }

    /** Applies to every {@code RestClient.Builder} injected from the context. */
    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(RestClientCustomizer.class)
    static class RestClientPropagation {

        @Bean
        RestClientCustomizer correlationIdRestClientCustomizer() {
            return builder -> builder.requestInterceptor(new CorrelationIdInterceptor());
        }
    }
}
