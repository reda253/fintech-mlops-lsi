package ma.fintech.customer.service;

import java.nio.file.Path;
import java.sql.Date;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import ma.fintech.customer.config.CustomerProperties;
import ma.fintech.customer.domain.Customer;
import ma.fintech.customer.repository.CustomerRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * Loads the Sparkov cardholders at startup (D50) from {@code CUSTOMER_SEED_PATH}, so the card numbers
 * the simulator replays resolve through {@code /internal/customers/lookup}. Runs before the readiness
 * probe turns UP. Skipped when no path is set or the table already has rows; all-or-nothing in one
 * transaction; {@code ON CONFLICT DO NOTHING} keeps it safe when several replicas start together.
 */
@Component
public class CustomerSeeder implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(CustomerSeeder.class);
    private static final int BATCH = 500;
    private static final String INSERT = """
            INSERT INTO customers (id, card_fingerprint, card_last4, first_name, last_name, gender, dob, job,
                                   street, city, state, zip, city_pop, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (card_fingerprint) DO NOTHING""";

    private final CustomerProperties properties;
    private final CustomerRepository customers;
    private final CardFingerprinter fingerprinter;
    private final JdbcTemplate jdbc;
    private final TransactionTemplate transaction;

    public CustomerSeeder(CustomerProperties properties, CustomerRepository customers,
                          CardFingerprinter fingerprinter, JdbcTemplate jdbc, TransactionTemplate transaction) {
        this.properties = properties;
        this.customers = customers;
        this.fingerprinter = fingerprinter;
        this.jdbc = jdbc;
        this.transaction = transaction;
    }

    @Override
    public void run(ApplicationArguments args) {
        seed();
    }

    /** Returns how many customers were inserted. */
    public int seed() {
        String seedPath = properties.seedPath();
        if (seedPath == null || seedPath.isBlank()) {
            log.info("Customer seed skipped: CUSTOMER_SEED_PATH is not set");
            return 0;
        }
        if (customers.count() > 0) {
            log.info("Customer seed skipped: customers already loaded");
            return 0;
        }
        List<Path> files = Arrays.stream(seedPath.split(",")).map(String::trim).filter(s -> !s.isEmpty())
                .map(Path::of).toList();
        Map<String, Customer.Profile> byCard = SparkovCustomerReader.read(files);

        List<Object[]> rows = new ArrayList<>(byCard.size());
        byCard.forEach((card, p) -> rows.add(new Object[] {
                UUID.randomUUID(), fingerprinter.fingerprint(card), CardFingerprinter.last4(card),
                p.firstName(), p.lastName(), p.gender().name(), Date.valueOf(p.dob()), p.job(),
                p.street(), p.city(), p.state(), p.zip(), p.cityPop(), p.latitude(), p.longitude()}));
        Integer inserted = transaction.execute(status -> {
            int total = 0;
            for (int from = 0; from < rows.size(); from += BATCH) {
                for (int n : jdbc.batchUpdate(INSERT, rows.subList(from, Math.min(from + BATCH, rows.size())))) {
                    total += Math.max(n, 0);
                }
            }
            return total;
        });
        log.info("Customer seed loaded {} customer(s) from {} file(s)", inserted, files.size());
        return inserted == null ? 0 : inserted;
    }
}
