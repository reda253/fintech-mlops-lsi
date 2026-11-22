package ma.fintech.customer.service;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/**
 * Card identifier = HMAC-SHA256(card number) with a key held only by customer-service (§3.4, §6.9).
 * A plain SHA-256 would not do: card numbers have so few possible values that every hash could be
 * reversed by brute force. Without the key, a leaked table reveals nothing.
 */
public class CardFingerprinter {

    static final int MIN_KEY_BYTES = 32;
    private static final String ALGORITHM = "HmacSHA256";

    private final SecretKeySpec key;

    public CardFingerprinter(String key) {
        if (key == null || key.getBytes(StandardCharsets.UTF_8).length < MIN_KEY_BYTES) {
            throw new IllegalStateException(
                    "CARD_HMAC_KEY must be set and at least " + MIN_KEY_BYTES + " bytes long");
        }
        this.key = new SecretKeySpec(key.getBytes(StandardCharsets.UTF_8), ALGORITHM);
    }

    /** 64 lowercase hex characters, the value of {@code customers.card_fingerprint}. */
    public String fingerprint(String cardNumber) {
        try {
            Mac mac = Mac.getInstance(ALGORITHM);    // not thread-safe: one per call
            mac.init(key);
            return HexFormat.of().formatHex(mac.doFinal(cardNumber.getBytes(StandardCharsets.US_ASCII)));
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException(e);      // HmacSHA256 ships with every JVM
        }
    }

    public static String last4(String cardNumber) {
        return cardNumber.substring(cardNumber.length() - 4);
    }
}
