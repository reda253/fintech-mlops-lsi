package ma.fintech.customer.service;

import java.util.Optional;
import java.util.UUID;

import ma.fintech.customer.domain.Customer;
import ma.fintech.customer.repository.CustomerRepository;
import ma.fintech.customer.repository.CustomerSpecs;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class CustomerService {

    private final CustomerRepository customers;
    private final CardFingerprinter fingerprinter;

    public CustomerService(CustomerRepository customers, CardFingerprinter fingerprinter) {
        this.customers = customers;
        this.fingerprinter = fingerprinter;
    }

    @Transactional(readOnly = true)
    public Page<Customer> list(String name, String city, String state, String cardLast4, Pageable pageable) {
        return customers.findAll(CustomerSpecs.matching(name, city, state, cardLast4), pageable);
    }

    @Transactional(readOnly = true)
    public Customer get(UUID id) {
        return customers.findById(id).orElseThrow(() -> notFound("Customer " + id + " not found"));
    }

    /** 409 if the card already belongs to a customer (pre-check, and the unique index for races). */
    @Transactional
    public Customer create(String cardNumber, Customer.Profile profile) {
        String fingerprint = fingerprinter.fingerprint(cardNumber);
        if (customers.existsByCardFingerprint(fingerprint)) {
            throw cardTaken();
        }
        try {
            return customers.saveAndFlush(new Customer(fingerprint, CardFingerprinter.last4(cardNumber), profile));
        } catch (DataIntegrityViolationException e) {
            throw cardTaken();
        }
    }

    /** The card cannot change; a concurrent edit ends in 409 (optimistic lock, handled by the advice). */
    @Transactional
    public Customer update(UUID id, Customer.Profile profile) {
        Customer customer = get(id);
        customer.apply(profile);
        return customers.saveAndFlush(customer);
    }

    /** D33: transaction-service sends the raw card number; only the fingerprint is compared. */
    @Transactional(readOnly = true)
    public Optional<Customer> findByCard(String cardNumber) {
        return customers.findByCardFingerprint(fingerprinter.fingerprint(cardNumber));
    }

    private static ResponseStatusException cardTaken() {
        return new ResponseStatusException(HttpStatus.CONFLICT, "This card already belongs to a customer");
    }

    static ResponseStatusException notFound(String detail) {
        return new ResponseStatusException(HttpStatus.NOT_FOUND, detail);
    }
}
