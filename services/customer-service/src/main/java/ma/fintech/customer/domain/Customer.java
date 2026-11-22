package ma.fintech.customer.domain;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.annotations.UpdateTimestamp;
import org.hibernate.type.SqlTypes;

/**
 * A cardholder (table {@code customer.customers}). The card number is never stored: only its
 * HMAC-SHA256 fingerprint, which identifies the card, and the last 4 digits for display (§3.4).
 */
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @JdbcTypeCode(SqlTypes.CHAR)
    @Column(nullable = false, unique = true, length = 64, updatable = false)
    private String cardFingerprint;

    @JdbcTypeCode(SqlTypes.CHAR)
    @Column(nullable = false, length = 4, updatable = false)
    private String cardLast4;

    @Column(nullable = false, length = 64)
    private String firstName;

    @Column(nullable = false, length = 64)
    private String lastName;

    @Enumerated(EnumType.STRING)
    @JdbcTypeCode(SqlTypes.CHAR)
    @Column(nullable = false, length = 1)
    private Gender gender;

    @Column(nullable = false)
    private LocalDate dob;

    @Column(nullable = false, length = 128)
    private String job;

    @Column(nullable = false, length = 128)
    private String street;

    @Column(nullable = false, length = 64)
    private String city;

    @JdbcTypeCode(SqlTypes.CHAR)
    @Column(nullable = false, length = 2)
    private String state;

    @Column(nullable = false, length = 10)
    private String zip;

    @Column(nullable = false)
    private int cityPop;

    @Column(nullable = false)
    private double latitude;

    @Column(nullable = false)
    private double longitude;

    @CreationTimestamp
    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    @UpdateTimestamp
    @Column(nullable = false)
    private Instant updatedAt;

    /** Optimistic lock: two admins editing the same customer cannot overwrite each other silently. */
    @Version
    @Column(nullable = false)
    private long version;

    protected Customer() {
        // JPA
    }

    public Customer(String cardFingerprint, String cardLast4, Profile profile) {
        this.cardFingerprint = cardFingerprint;
        this.cardLast4 = cardLast4;
        apply(profile);
    }

    /** Updates every profile field. The card (fingerprint, last 4) never changes. */
    public void apply(Profile p) {
        this.firstName = p.firstName();
        this.lastName = p.lastName();
        this.gender = p.gender();
        this.dob = p.dob();
        this.job = p.job();
        this.street = p.street();
        this.city = p.city();
        this.state = p.state();
        this.zip = p.zip();
        this.cityPop = p.cityPop();
        this.latitude = p.latitude();
        this.longitude = p.longitude();
    }

    /** The editable part of a customer, shared by create, update and the Sparkov seed. */
    public record Profile(String firstName, String lastName, Gender gender, LocalDate dob, String job,
                          String street, String city, String state, String zip, int cityPop,
                          double latitude, double longitude) {
    }

    public UUID getId() { return id; }
    public String getCardFingerprint() { return cardFingerprint; }
    public String getCardLast4() { return cardLast4; }
    public String getFirstName() { return firstName; }
    public String getLastName() { return lastName; }
    public Gender getGender() { return gender; }
    public LocalDate getDob() { return dob; }
    public String getJob() { return job; }
    public String getStreet() { return street; }
    public String getCity() { return city; }
    public String getState() { return state; }
    public String getZip() { return zip; }
    public int getCityPop() { return cityPop; }
    public double getLatitude() { return latitude; }
    public double getLongitude() { return longitude; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public long getVersion() { return version; }
}
