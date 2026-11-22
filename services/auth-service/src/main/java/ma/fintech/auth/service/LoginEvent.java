package ma.fintech.auth.service;

import java.util.UUID;

/**
 * Payload of {@code auth.login.succeeded} / {@code auth.login.failed} (contracts/events.md).
 * Never carries the password; the IP is out of scope.
 *
 * @param userId   {@code null} when the username does not exist
 * @param username the username that was tried
 * @param reason   {@code null} on success
 */
record LoginEvent(UUID userId, String username, Reason reason) {

    enum Reason { BAD_CREDENTIALS, DISABLED }
}
