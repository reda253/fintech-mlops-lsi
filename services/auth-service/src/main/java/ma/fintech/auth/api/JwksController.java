package ma.fintech.auth.api;

import java.util.Map;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** Public signing keys, fetched by the gateway and every service. Never routed by the gateway. */
@RestController
class JwksController {

    private final Map<String, Object> jwks;

    JwksController(RSAKey signingKey) {
        this.jwks = new JWKSet(signingKey.toPublicJWK()).toJSONObject();
    }

    @GetMapping("/.well-known/jwks.json")
    Map<String, Object> jwks() {
        return jwks;
    }
}
