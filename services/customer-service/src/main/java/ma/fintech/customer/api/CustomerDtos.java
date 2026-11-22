package ma.fintech.customer.api;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Past;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;
import ma.fintech.customer.domain.Customer;
import ma.fintech.customer.domain.Gender;

/** Request and response bodies of contracts/customer-service.yaml. */
final class CustomerDtos {

    /** Sparkov card numbers have 11 to 19 digits. */
    static final String CARD_NUMBER = "^\\d{11,19}$";

    private CustomerDtos() {
    }

    /** {@code CustomerProfile}. JSON {@code long} is a Java keyword, hence {@code lng}. */
    record CustomerProfile(
            @NotBlank @Size(max = 64) String firstName,
            @NotBlank @Size(max = 64) String lastName,
            @NotNull Gender gender,
            @NotNull @Past LocalDate dob,
            @NotBlank @Size(max = 128) String job,
            @NotBlank @Size(max = 128) String street,
            @NotBlank @Size(max = 64) String city,
            @NotNull @Pattern(regexp = "^[A-Z]{2}$") String state,
            @NotBlank @Size(max = 10) String zip,
            @NotNull @PositiveOrZero Integer cityPop,
            @NotNull @DecimalMin("-90") @DecimalMax("90") Double lat,
            @JsonProperty("long") @NotNull @DecimalMin("-180") @DecimalMax("180") Double lng) {

        Customer.Profile toDomain() {
            return new Customer.Profile(firstName, lastName, gender, dob, job, street, city, state, zip,
                    cityPop, lat, lng);
        }
    }

    /**
     * {@code CreateCustomerRequest} = profile + card number. The card number is write-only: it is
     * fingerprinted and dropped, and {@link #toString()} never prints it.
     */
    record CreateCustomerRequest(
            @NotNull @Pattern(regexp = CARD_NUMBER) String cardNumber,
            @NotBlank @Size(max = 64) String firstName,
            @NotBlank @Size(max = 64) String lastName,
            @NotNull Gender gender,
            @NotNull @Past LocalDate dob,
            @NotBlank @Size(max = 128) String job,
            @NotBlank @Size(max = 128) String street,
            @NotBlank @Size(max = 64) String city,
            @NotNull @Pattern(regexp = "^[A-Z]{2}$") String state,
            @NotBlank @Size(max = 10) String zip,
            @NotNull @PositiveOrZero Integer cityPop,
            @NotNull @DecimalMin("-90") @DecimalMax("90") Double lat,
            @JsonProperty("long") @NotNull @DecimalMin("-180") @DecimalMax("180") Double lng) {

        Customer.Profile toDomain() {
            return new Customer.Profile(firstName, lastName, gender, dob, job, street, city, state, zip,
                    cityPop, lat, lng);
        }

        @Override
        public String toString() {
            return "CreateCustomerRequest[cardNumber=****, lastName=" + lastName + "]";
        }
    }

    record CustomerResponse(
            UUID id, String cardLast4, Instant createdAt, Instant updatedAt,
            String firstName, String lastName, Gender gender, LocalDate dob, String job,
            String street, String city, String state, String zip, int cityPop,
            double lat, @JsonProperty("long") double lng) {

        static CustomerResponse from(Customer c) {
            return new CustomerResponse(c.getId(), c.getCardLast4(), c.getCreatedAt(), c.getUpdatedAt(),
                    c.getFirstName(), c.getLastName(), c.getGender(), c.getDob(), c.getJob(),
                    c.getStreet(), c.getCity(), c.getState(), c.getZip(), c.getCityPop(),
                    c.getLatitude(), c.getLongitude());
        }
    }

    record LookupRequest(@NotNull @Pattern(regexp = CARD_NUMBER) String cardNumber) {

        @Override
        public String toString() {
            return "LookupRequest[cardNumber=****]";
        }
    }

    record LookupResponse(UUID customerId, String cardLast4) {
    }

    /** Exactly the {@code customer} object of ml-service {@code /predict} (D34, data minimisation). */
    record RiskProfile(UUID customerId, LocalDate dob, Gender gender, int cityPop, double lat,
                       @JsonProperty("long") double lng, String state) {

        static RiskProfile from(Customer c) {
            return new RiskProfile(c.getId(), c.getDob(), c.getGender(), c.getCityPop(),
                    c.getLatitude(), c.getLongitude(), c.getState());
        }
    }
}
