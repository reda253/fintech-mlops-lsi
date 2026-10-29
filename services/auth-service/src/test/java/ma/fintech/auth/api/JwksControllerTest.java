package ma.fintech.auth.api;

import java.time.Instant;
import java.util.List;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import ma.fintech.auth.TestcontainersConfig;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(TestcontainersConfig.class)
class JwksControllerTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    JwtEncoder encoder;

    @Test
    void tokenSignedHereVerifiesWithThePublishedJwksOnly() throws Exception {
        // What any other service does: fetch the JWKS without a token...
        String body = mvc.perform(get("/.well-known/jwks.json"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        RSAKey published = (RSAKey) JWKSet.parse(body).getKeys().getFirst();

        // ...which must never leak the private key.
        assertThat(published.isPrivate()).isFalse();
        assertThat(published.getKeyID()).isNotBlank();
        assertThat(published.getAlgorithm().getName()).isEqualTo("RS256");

        // ...then verify a token signed by auth-service with nothing but that public key.
        JwtClaimsSet claims = JwtClaimsSet.builder()
                .subject("user-1")
                .claim("roles", List.of("ANALYSTE"))
                .expiresAt(Instant.now().plusSeconds(60))
                .build();
        String token = encoder.encode(JwtEncoderParameters.from(
                JwsHeader.with(SignatureAlgorithm.RS256).keyId(published.getKeyID()).build(), claims)).getTokenValue();

        Jwt decoded = NimbusJwtDecoder.withPublicKey(published.toRSAPublicKey()).build().decode(token);
        assertThat(decoded.getSubject()).isEqualTo("user-1");
        assertThat(decoded.getClaimAsStringList("roles")).containsExactly("ANALYSTE");
    }
}
