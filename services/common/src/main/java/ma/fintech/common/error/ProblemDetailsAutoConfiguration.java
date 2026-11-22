package ma.fintech.common.error;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Runs before Boot's WebMvc auto-configuration, whose own Problem Details handler then backs off. */
@AutoConfiguration(beforeName = "org.springframework.boot.webmvc.autoconfigure.WebMvcAutoConfiguration")
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
public class ProblemDetailsAutoConfiguration {

    @Bean
    GlobalExceptionHandler globalExceptionHandler() {
        return new GlobalExceptionHandler();
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "org.springframework.dao.OptimisticLockingFailureException")
    static class OptimisticLock {

        @Bean
        OptimisticLockExceptionHandler optimisticLockExceptionHandler() {
            return new OptimisticLockExceptionHandler();
        }
    }
}
