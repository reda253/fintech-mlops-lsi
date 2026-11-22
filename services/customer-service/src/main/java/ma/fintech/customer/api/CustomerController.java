package ma.fintech.customer.api;

import java.net.URI;
import java.util.Set;
import java.util.UUID;

import jakarta.validation.Valid;
import ma.fintech.customer.api.CustomerDtos.CreateCustomerRequest;
import ma.fintech.customer.api.CustomerDtos.CustomerProfile;
import ma.fintech.customer.api.CustomerDtos.CustomerResponse;
import ma.fintech.customer.service.CustomerService;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PagedModel;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/** Public CRUD. Roles (contracts/gateway-routes.md) are in {@code SecurityRules}. */
@RestController
@RequestMapping("/api/v1/customers")
class CustomerController {

    /** Sortable properties; anything else is a 400 rather than a query on an arbitrary column. */
    static final Set<String> SORTABLE = Set.of("lastName", "firstName", "city", "state", "createdAt");

    private final CustomerService customers;

    CustomerController(CustomerService customers) {
        this.customers = customers;
    }

    @GetMapping
    PagedModel<CustomerResponse> list(@RequestParam(required = false) String name,
                                      @RequestParam(required = false) String city,
                                      @RequestParam(required = false) String state,
                                      @RequestParam(required = false) String cardLast4,
                                      Pageable pageable) {
        for (Sort.Order order : pageable.getSort()) {
            if (!SORTABLE.contains(order.getProperty())) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                        "Cannot sort by '" + order.getProperty() + "'. Allowed: " + SORTABLE);
            }
        }
        return new PagedModel<>(customers.list(name, city, state, cardLast4, pageable).map(CustomerResponse::from));
    }

    @PostMapping
    ResponseEntity<CustomerResponse> create(@Valid @RequestBody CreateCustomerRequest request) {
        CustomerResponse created = CustomerResponse.from(customers.create(request.cardNumber(), request.toDomain()));
        return ResponseEntity.created(URI.create("/api/v1/customers/" + created.id())).body(created);
    }

    @GetMapping("/{id}")
    CustomerResponse get(@PathVariable UUID id) {
        return CustomerResponse.from(customers.get(id));
    }

    @PutMapping("/{id}")
    CustomerResponse update(@PathVariable UUID id, @Valid @RequestBody CustomerProfile profile) {
        return CustomerResponse.from(customers.update(id, profile.toDomain()));
    }
}
