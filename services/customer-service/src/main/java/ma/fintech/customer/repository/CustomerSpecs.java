package ma.fintech.customer.repository;

import java.util.Locale;
import java.util.Objects;
import java.util.stream.Stream;

import ma.fintech.customer.domain.Customer;
import org.springframework.data.jpa.domain.Specification;

/** Filters of {@code GET /api/v1/customers}. A {@code null} or blank value means "no filter". */
public final class CustomerSpecs {

    private CustomerSpecs() {
    }

    public static Specification<Customer> matching(String name, String city, String state, String cardLast4) {
        // Spring Data 4 rejects null parts, so absent filters are dropped; none left = every customer.
        return Specification.allOf(Stream.of(nameContains(name), cityIs(city), stateIs(state), cardLast4Is(cardLast4))
                .filter(Objects::nonNull)
                .toList());
    }

    /** Case-insensitive match on the first or the last name. */
    static Specification<Customer> nameContains(String name) {
        if (isBlank(name)) {
            return null;
        }
        String pattern = "%" + escapeLike(name.trim().toLowerCase(Locale.ROOT)) + "%";
        return (root, query, cb) -> cb.or(
                cb.like(cb.lower(root.get("firstName")), pattern, '\\'),
                cb.like(cb.lower(root.get("lastName")), pattern, '\\'));
    }

    static Specification<Customer> cityIs(String city) {
        return isBlank(city) ? null
                : (root, query, cb) -> cb.equal(cb.lower(root.get("city")), city.trim().toLowerCase(Locale.ROOT));
    }

    static Specification<Customer> stateIs(String state) {
        return isBlank(state) ? null : (root, query, cb) -> cb.equal(root.get("state"), state);
    }

    static Specification<Customer> cardLast4Is(String cardLast4) {
        return isBlank(cardLast4) ? null : (root, query, cb) -> cb.equal(root.get("cardLast4"), cardLast4);
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    /** {@code %} and {@code _} typed by the user are literal characters, not wildcards. */
    private static String escapeLike(String value) {
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_");
    }
}
