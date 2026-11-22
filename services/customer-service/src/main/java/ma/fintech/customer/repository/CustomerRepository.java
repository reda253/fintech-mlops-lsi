package ma.fintech.customer.repository;

import java.util.Optional;
import java.util.UUID;

import ma.fintech.customer.domain.Customer;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface CustomerRepository extends JpaRepository<Customer, UUID>, JpaSpecificationExecutor<Customer> {

    Optional<Customer> findByCardFingerprint(String cardFingerprint);

    boolean existsByCardFingerprint(String cardFingerprint);
}
