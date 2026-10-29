package ma.fintech.auth.config;

import java.security.KeyFactory;
import java.security.interfaces.RSAPrivateCrtKey;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.RSAPublicKeySpec;

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.KeyUse;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import ma.fintech.common.security.AuthorizationRules;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

/**
 * RS256 signing key, password hashing and the public endpoints. Only the private key is configured
 * (PKCS#8 PEM, from a K8s Secret in production); the public key is derived from it (D41).
 */
@Configuration(proxyBeanMethods = false)
public class SecurityConfig {

    @Bean
    RSAKey signingKey(@Value("${jwt.private-key}") RSAPrivateKey privateKey) throws Exception {
        RSAPrivateCrtKey crt = (RSAPrivateCrtKey) privateKey;
        RSAPublicKey publicKey = (RSAPublicKey) KeyFactory.getInstance("RSA")
                .generatePublic(new RSAPublicKeySpec(crt.getModulus(), crt.getPublicExponent()));
        return new RSAKey.Builder(publicKey)
                .privateKey(privateKey)
                .keyUse(KeyUse.SIGNATURE)
                .algorithm(JWSAlgorithm.RS256)
                .keyIDFromThumbprint()    // stable kid (RFC 7638): every replica publishes the same one
                .build();
    }

    @Bean
    JwtEncoder jwtEncoder(RSAKey signingKey) {
        return new NimbusJwtEncoder(new ImmutableJWKSet<>(new JWKSet(signingKey)));
    }

    /** auth-service verifies its own tokens with the local key instead of fetching its own JWKS over HTTP. */
    @Bean
    JwtDecoder jwtDecoder(RSAKey signingKey) throws Exception {
        return NimbusJwtDecoder.withPublicKey(signingKey.toRSAPublicKey()).build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();    // cost 10 (default), ~100 ms per check
    }

    @Bean
    AuthorizationRules authRules() {
        return rules -> rules
                .requestMatchers(HttpMethod.GET, "/.well-known/jwks.json").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/v1/auth/login", "/api/v1/auth/refresh").permitAll()
                .requestMatchers("/api/v1/auth/users/**").hasRole("ADMIN");
    }
}
