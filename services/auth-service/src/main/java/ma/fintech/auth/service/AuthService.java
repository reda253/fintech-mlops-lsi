package ma.fintech.auth.service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;

import ma.fintech.auth.api.TokenResponse;
import ma.fintech.auth.domain.RefreshToken;
import ma.fintech.auth.domain.User;
import ma.fintech.auth.repository.RefreshTokenRepository;
import ma.fintech.auth.repository.UserRepository;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AuthService {

    public static final String ISSUER = "fintech-auth";
    static final Duration ACCESS_TTL = Duration.ofMinutes(15);   // contract: auth-service.yaml
    static final Duration REFRESH_TTL = Duration.ofDays(7);

    private static final SecureRandom RANDOM = new SecureRandom();

    private final UserRepository users;
    private final RefreshTokenRepository refreshTokens;
    private final PasswordEncoder passwordEncoder;
    private final JwtEncoder jwtEncoder;
    private final String dummyHash;

    public AuthService(UserRepository users, RefreshTokenRepository refreshTokens,
                       PasswordEncoder passwordEncoder, JwtEncoder jwtEncoder) {
        this.users = users;
        this.refreshTokens = refreshTokens;
        this.passwordEncoder = passwordEncoder;
        this.jwtEncoder = jwtEncoder;
        this.dummyHash = passwordEncoder.encode("timing-equalizer");
    }

    /**
     * Unknown user, wrong password and disabled account all get the same 401, and BCrypt always runs,
     * so neither the message nor the response time reveals which usernames exist.
     */
    @Transactional
    public TokenResponse login(String username, String password) {
        User user = users.findByUsername(username).orElse(null);
        boolean passwordOk = passwordEncoder.matches(password, user != null ? user.getPasswordHash() : dummyHash);
        if (user == null || !passwordOk || !user.isEnabled()) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Invalid username or password");
        }
        return issueTokens(user);
    }

    /**
     * Rotation: the presented token is revoked and a new pair issued. A token that is already revoked
     * means it was copied (the legitimate client already rotated it), so every token of that user is
     * revoked and both the thief and the victim must log in again. noRollbackFor keeps that revocation.
     */
    @Transactional(noRollbackFor = ResponseStatusException.class)
    public TokenResponse refresh(String token) {
        Instant now = Instant.now();
        RefreshToken stored = refreshTokens.findByTokenHash(sha256(token)).orElseThrow(AuthService::invalidRefresh);
        if (stored.getRevokedAt() != null) {
            refreshTokens.revokeAllByUserId(stored.getUserId(), now);
            throw invalidRefresh();
        }
        if (!now.isBefore(stored.getExpiresAt())) {
            throw invalidRefresh();
        }
        User user = users.findById(stored.getUserId()).filter(User::isEnabled).orElseThrow(AuthService::invalidRefresh);
        stored.revoke(now);
        return issueTokens(user);
    }

    private static ResponseStatusException invalidRefresh() {
        return new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Invalid refresh token");
    }

    private TokenResponse issueTokens(User user) {
        Instant now = Instant.now();
        JwtClaimsSet claims = JwtClaimsSet.builder()
                .issuer(ISSUER)
                .subject(user.getId().toString())
                .claim("preferred_username", user.getUsername())
                .claim("roles", user.getRoles().stream().map(Enum::name).toList())
                .issuedAt(now)
                .expiresAt(now.plus(ACCESS_TTL))
                .build();
        String accessToken = jwtEncoder.encode(
                JwtEncoderParameters.from(JwsHeader.with(SignatureAlgorithm.RS256).build(), claims)).getTokenValue();

        byte[] random = new byte[32];
        RANDOM.nextBytes(random);
        String refreshToken = Base64.getUrlEncoder().withoutPadding().encodeToString(random);
        refreshTokens.save(new RefreshToken(user.getId(), sha256(refreshToken), now.plus(REFRESH_TTL)));

        return new TokenResponse(accessToken, refreshToken, "Bearer",
                ACCESS_TTL.toSeconds(), REFRESH_TTL.toSeconds());
    }

    /** Hex SHA-256: refresh tokens are 256-bit random, so a fast hash is enough (no BCrypt needed). */
    public static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);    // every JVM ships SHA-256
        }
    }
}
