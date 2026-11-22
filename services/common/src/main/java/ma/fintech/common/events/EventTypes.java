package ma.fintech.common.events;

/** Event types = routing keys on {@code fintech.events} (contracts/events.md). */
public final class EventTypes {

    public static final String TRANSACTION_APPROVED = "transaction.decided.approved";
    public static final String TRANSACTION_REVIEW = "transaction.decided.review";
    public static final String TRANSACTION_BLOCKED = "transaction.decided.blocked";
    public static final String REVIEW_COMPLETED = "review.completed";
    public static final String LOGIN_SUCCEEDED = "auth.login.succeeded";
    public static final String LOGIN_FAILED = "auth.login.failed";

    private EventTypes() {
    }
}
