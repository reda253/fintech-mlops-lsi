package ma.fintech.auth.api;

import java.net.URI;
import java.util.Set;
import java.util.UUID;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import ma.fintech.auth.domain.User.Role;
import ma.fintech.auth.service.UserService;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedModel;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.http.HttpStatus.NO_CONTENT;

/** {@code /me} is open to any authenticated user; {@code /users/**} is ADMIN only (SecurityConfig). */
@RestController
@RequestMapping("/api/v1/auth")
class UserController {

    record CreateUserRequest(@NotNull @Size(min = 3, max = 64) String username,
                             @NotNull @Size(min = 8, max = 128) String password,
                             @NotEmpty Set<Role> roles) {
    }

    record UpdateUserRequest(@Size(min = 8, max = 128) String password,
                             @Size(min = 1) Set<Role> roles,
                             Boolean enabled) {
    }

    private final UserService users;

    UserController(UserService users) {
        this.users = users;
    }

    @GetMapping("/me")
    UserResponse me(@AuthenticationPrincipal Jwt jwt) {
        return UserResponse.from(users.get(UUID.fromString(jwt.getSubject())));
    }

    @GetMapping("/users")
    PagedModel<UserResponse> list(@RequestParam(required = false) Role role, Pageable pageable) {
        return new PagedModel<>(users.list(role, pageable).map(UserResponse::from));
    }

    @PostMapping("/users")
    ResponseEntity<UserResponse> create(@Valid @RequestBody CreateUserRequest request) {
        UserResponse created = UserResponse.from(users.create(request.username(), request.password(), request.roles()));
        return ResponseEntity.created(URI.create("/api/v1/auth/users/" + created.id())).body(created);
    }

    @GetMapping("/users/{id}")
    UserResponse get(@PathVariable UUID id) {
        return UserResponse.from(users.get(id));
    }

    @PutMapping("/users/{id}")
    UserResponse update(@PathVariable UUID id, @Valid @RequestBody UpdateUserRequest request) {
        return UserResponse.from(users.update(id, request.password(), request.roles(), request.enabled()));
    }

    @DeleteMapping("/users/{id}")
    @ResponseStatus(NO_CONTENT)
    void disable(@PathVariable UUID id) {
        users.disable(id);
    }
}
