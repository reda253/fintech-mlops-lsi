package ma.fintech.auth.service;

import java.time.Instant;
import java.util.Set;
import java.util.UUID;

import ma.fintech.auth.domain.User;
import ma.fintech.auth.domain.User.Role;
import ma.fintech.auth.repository.RefreshTokenRepository;
import ma.fintech.auth.repository.UserRepository;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
@Transactional
public class UserService {

    private final UserRepository users;
    private final RefreshTokenRepository refreshTokens;
    private final PasswordEncoder passwordEncoder;

    public UserService(UserRepository users, RefreshTokenRepository refreshTokens, PasswordEncoder passwordEncoder) {
        this.users = users;
        this.refreshTokens = refreshTokens;
        this.passwordEncoder = passwordEncoder;
    }

    @Transactional(readOnly = true)
    public Page<User> list(Role role, Pageable pageable) {
        return role == null ? users.findAll(pageable) : users.findByRole(role.name(), pageable);
    }

    public User get(UUID id) {
        return users.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "User not found"));
    }

    public User create(String username, String password, Set<Role> roles) {
        // The UNIQUE constraint is the only check, so two concurrent creates of one name still give 409, not 500.
        // Flush now so the violation is raised here and not at commit, outside this try.
        try {
            return users.saveAndFlush(new User(username, passwordEncoder.encode(password), roles));
        } catch (DataIntegrityViolationException e) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Username already taken");
        }
    }

    /** Null fields are left unchanged. A new password or a disabled account ends every open session. */
    public User update(UUID id, String password, Set<Role> roles, Boolean enabled) {
        User user = get(id);
        if (roles != null) {
            user.setRoles(roles);
        }
        if (password != null) {
            user.setPasswordHash(passwordEncoder.encode(password));
        }
        if (enabled != null) {
            user.setEnabled(enabled);
        }
        if (password != null || !user.isEnabled()) {
            refreshTokens.revokeAllByUserId(id, Instant.now());
        }
        return user;
    }

    /** Soft delete: the row stays so audit events keep pointing at a real actor. */
    public void disable(UUID id) {
        update(id, null, null, false);
    }
}
