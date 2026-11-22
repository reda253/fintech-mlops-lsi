package ma.fintech.customer.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * {@code customer.*}.
 *
 * @param cardHmacKey HMAC-SHA256 key for card fingerprints (env {@code CARD_HMAC_KEY}, K8s Secret).
 *                    Never logged, never in a ConfigMap. Changing it orphans every stored fingerprint.
 * @param seedPath    comma-separated Sparkov CSV files to load at startup (env {@code CUSTOMER_SEED_PATH});
 *                    blank = no seed
 */
@ConfigurationProperties("customer")
public record CustomerProperties(String cardHmacKey, String seedPath) {
}
