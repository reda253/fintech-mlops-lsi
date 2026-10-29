package ma.fintech.auth.api;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import ma.fintech.auth.service.AuthService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/auth")
class AuthController {

    record LoginRequest(@NotNull @Size(min = 3, max = 64) String username,
                        @NotNull @Size(min = 8, max = 128) String password) {
    }

    record RefreshRequest(@NotBlank @Size(max = 128) String refreshToken) {
    }

    private final AuthService auth;

    AuthController(AuthService auth) {
        this.auth = auth;
    }

    @PostMapping("/login")
    TokenResponse login(@Valid @RequestBody LoginRequest request) {
        return auth.login(request.username(), request.password());
    }

    @PostMapping("/refresh")
    TokenResponse refresh(@Valid @RequestBody RefreshRequest request) {
        return auth.refresh(request.refreshToken());
    }
}
