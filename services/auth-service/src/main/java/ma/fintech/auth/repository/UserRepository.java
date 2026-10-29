package ma.fintech.auth.repository;

import java.util.Optional;
import java.util.UUID;

import ma.fintech.auth.domain.User;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserRepository extends JpaRepository<User, UUID> {

    Optional<User> findByUsername(String username);
}
