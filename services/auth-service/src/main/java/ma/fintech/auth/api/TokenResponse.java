package ma.fintech.auth.api;

public record TokenResponse(String accessToken, String refreshToken, String tokenType,
                            long expiresIn, long refreshExpiresIn) {
}
