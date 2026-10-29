package ma.fintech.auth.repository;

import java.util.Optional;
import java.util.UUID;

import ma.fintech.auth.domain.User;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface UserRepository extends JpaRepository<User, UUID> {

    Optional<User> findByUsername(String username);

    // String, not Role: Hibernate binds an enum parameter inside array_contains as its ordinal (smallint).
    @Query("select u from User u where array_contains(u.roles, :role)")
    Page<User> findByRole(String role, Pageable pageable);
}
