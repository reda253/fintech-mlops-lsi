package ma.fintech.customer.api;

import java.util.UUID;

import jakarta.validation.Valid;
import ma.fintech.customer.api.CustomerDtos.LookupRequest;
import ma.fintech.customer.api.CustomerDtos.LookupResponse;
import ma.fintech.customer.api.CustomerDtos.RiskProfile;
import ma.fintech.customer.service.CustomerService;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/**
 * Service-to-service endpoints, never routed by the gateway. Any valid JWT is accepted (the
 * caller propagates the user's token); who may call is restricted by NetworkPolicy (gateway-routes.md).
 */
@RestController
@RequestMapping("/internal/customers")
class InternalCustomerController {

    private final CustomerService customers;

    InternalCustomerController(CustomerService customers) {
        this.customers = customers;
    }

    /** D33. POST so the card number never appears in a URL or an access log. */
    @PostMapping("/lookup")
    LookupResponse lookup(@Valid @RequestBody LookupRequest request) {
        return customers.findByCard(request.cardNumber())
                .map(c -> new LookupResponse(c.getId(), c.getCardLast4()))
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "No customer for this card"));
    }

    /** D34: only the fields {@code /predict} needs. */
    @GetMapping("/{id}/risk-profile")
    RiskProfile riskProfile(@PathVariable UUID id) {
        return RiskProfile.from(customers.get(id));
    }
}
