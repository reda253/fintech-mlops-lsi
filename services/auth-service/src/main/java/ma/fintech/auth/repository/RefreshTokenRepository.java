package ma.fintech.auth.repository;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

import jakarta.persistence.LockModeType;
import ma.fintech.auth.domain.RefreshToken;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

public interface RefreshTokenRepository extends JpaRepository<RefreshToken, UUID> {

    /** SELECT ... FOR UPDATE: two parallel refreshes with the same token are serialized, only one wins. */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    Optional<RefreshToken> findByTokenHash(String tokenHash);

    @Modifying
    @Query("update RefreshToken t set t.revokedAt = :at where t.userId = :userId and t.revokedAt is null")
    int revokeAllByUserId(UUID userId, Instant at);
}
