package ma.fintech.customer.service;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CardFingerprinterTest {

    private static final String KEY = "test-key-test-key-test-key-test-key!";
    private static final String CARD = "2291163933867244";

    @Test
    void sameCardAndKeyGiveTheSame64HexFingerprint() {
        String fingerprint = new CardFingerprinter(KEY).fingerprint(CARD);

        assertThat(fingerprint).hasSize(64).matches("[0-9a-f]{64}").doesNotContain(CARD);
        assertThat(new CardFingerprinter(KEY).fingerprint(CARD)).isEqualTo(fingerprint);
    }

    /** The key is the point: without it, a stolen table cannot be matched against card numbers. */
    @Test
    void anotherKeyGivesAnotherFingerprint() {
        String other = new CardFingerprinter("another-key-another-key-another-key!").fingerprint(CARD);

        assertThat(other).isNotEqualTo(new CardFingerprinter(KEY).fingerprint(CARD));
    }

    @Test
    void missingOrShortKeyStopsTheService() {
        assertThatThrownBy(() -> new CardFingerprinter(null)).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> new CardFingerprinter("")).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> new CardFingerprinter("too-short")).hasMessageContaining("CARD_HMAC_KEY");
    }

    @Test
    void last4() {
        assertThat(CardFingerprinter.last4(CARD)).isEqualTo("7244");
    }
}
