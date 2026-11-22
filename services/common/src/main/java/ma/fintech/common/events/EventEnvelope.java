package ma.fintech.common.events;

import java.time.Instant;
import java.util.UUID;

import tools.jackson.databind.JsonNode;

/**
 * The envelope every event travels in (contracts/events.md, events.schema.json).
 *
 * @param eventId       unique id, also the AMQP {@code message_id}; consumers dedupe on it
 * @param type          one of {@link EventTypes}, also the routing key on {@link Topology#EVENTS_EXCHANGE}
 * @param version       payload version; bumped only on a breaking change
 * @param occurredAt    when the business change happened (UTC)
 * @param correlationId the request that caused it, or {@code null} for scheduled work
 * @param producer      {@code spring.application.name} of the producing service
 * @param actor         username behind the change, {@code system} for automatic decisions
 * @param payload       event-specific body
 */
public record EventEnvelope(
        UUID eventId,
        String type,
        int version,
        Instant occurredAt,
        String correlationId,
        String producer,
        String actor,
        JsonNode payload) {
}
