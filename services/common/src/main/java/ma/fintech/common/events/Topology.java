package ma.fintech.common.events;

/** Exchange and queue names (contracts/events.md, "Topology"). Declared in code by {@code common/messaging}. */
public final class Topology {

    /** Topic exchange carrying every domain event; routing key = event type. */
    public static final String EVENTS_EXCHANGE = "fintech.events";

    /** Fanout used by notification-service to re-broadcast to every replica (live push only). */
    public static final String NOTIFICATIONS_LIVE_EXCHANGE = "notifications.live";

    /** Direct dead-letter exchange; routing key = the original queue name. */
    public static final String DEAD_LETTER_EXCHANGE = "fintech.dlx";

    public static final String AUDIT_QUEUE = "audit.all";
    public static final String NOTIFICATION_ALERTS_QUEUE = "notification.alerts";
    public static final String TRANSACTION_REVIEW_RESULTS_QUEUE = "transaction.review-results";

    private Topology() {
    }

    /** Name of the dead-letter queue paired with {@code queue}. */
    public static String dlq(String queue) {
        return queue + ".dlq";
    }
}
