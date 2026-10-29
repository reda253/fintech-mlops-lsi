package ma.fintech.auth.api;

import java.time.Instant;
import java.util.Set;
import java.util.UUID;

import ma.fintech.auth.domain.User;
import ma.fintech.auth.domain.User.Role;

/** Never exposes the password hash. */
public record UserResponse(UUID id, String username, Set<Role> roles, boolean enabled, Instant createdAt) {

    static UserResponse from(User user) {
        return new UserResponse(user.getId(), user.getUsername(), user.getRoles(), user.isEnabled(), user.getCreatedAt());
    }
}
