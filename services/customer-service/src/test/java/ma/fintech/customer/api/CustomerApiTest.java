package ma.fintech.customer.api;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;

import com.jayway.jsonpath.JsonPath;
import ma.fintech.customer.config.CustomerProperties;
import ma.fintech.customer.repository.CustomerRepository;
import ma.fintech.customer.service.CardFingerprinter;
import ma.fintech.customer.service.CustomerSeeder;
import ma.fintech.customer.service.SparkovCustomerReaderTest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.hasSize;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** customer-service against a real PostgreSQL (Flyway V1, Hibernate validate). Skipped without Docker. */
@SpringBootTest(properties = {
        "customer.card-hmac-key=test-key-test-key-test-key-test-key!",
        "spring.flyway.create-schemas=true"})
@AutoConfigureMockMvc
@Import(CustomerApiTest.Containers.class)
@Testcontainers(disabledWithoutDocker = true)
class CustomerApiTest {

    private static final String CARD = "4613314721966";

    @TestConfiguration(proxyBeanMethods = false)
    static class Containers {
        @Bean
        @ServiceConnection
        PostgreSQLContainer postgres() {
            return new PostgreSQLContainer("postgres:16-alpine");
        }
    }

    @Autowired MockMvc mvc;
    @Autowired CustomerRepository customers;
    @Autowired CardFingerprinter fingerprinter;
    @Autowired JdbcTemplate jdbc;
    @Autowired TransactionTemplate transaction;
    @MockitoBean JwtDecoder jwtDecoder;

    @BeforeEach
    void setUp() {
        customers.deleteAll();
        given(jwtDecoder.decode(anyString())).willAnswer(call -> switch (call.<String>getArgument(0)) {
            case "ADMIN", "ANALYSTE", "SIMULATEUR" -> jwt(call.getArgument(0));
            default -> throw new BadJwtException("bad signature");
        });
    }

    // ---- security (role matrix, contracts/gateway-routes.md)

    @Test
    void rolesFollowTheMatrix() throws Exception {
        mvc.perform(get("/api/v1/customers")).andExpect(status().isUnauthorized());
        mvc.perform(as("SIMULATEUR", get("/api/v1/customers"))).andExpect(status().isForbidden());
        mvc.perform(as("ANALYSTE", get("/api/v1/customers"))).andExpect(status().isOk());
        create("ANALYSTE", CARD, "Jeff").andExpect(status().isForbidden());
        create("ADMIN", CARD, "Jeff").andExpect(status().isCreated());
    }

    /** Internal endpoints take the propagated caller token, whatever its role (D33, D34). */
    @Test
    void internalEndpointsAcceptAnyValidToken() throws Exception {
        create("ADMIN", CARD, "Jeff");
        mvc.perform(post("/internal/customers/lookup").contentType(MediaType.APPLICATION_JSON)
                .content("{\"cardNumber\":\"" + CARD + "\"}")).andExpect(status().isUnauthorized());
        lookup("SIMULATEUR", CARD).andExpect(status().isOk());
    }

    // ---- create / get / update

    @Test
    void createStoresOnlyTheFingerprintAndLast4() throws Exception {
        String body = create("ADMIN", CARD, "Jeff")
                .andExpect(status().isCreated())
                .andExpect(header().string(HttpHeaders.LOCATION, org.hamcrest.Matchers.startsWith("/api/v1/customers/")))
                .andExpect(jsonPath("$.cardLast4").value("1966"))
                .andExpect(jsonPath("$.cardNumber").doesNotExist())
                .andExpect(jsonPath("$.long").value(-80.9355))
                .andReturn().getResponse().getContentAsString();
        assertThat(body).doesNotContain(CARD);

        List<String> stored = jdbc.queryForList("SELECT card_fingerprint || card_last4 FROM customers", String.class);
        assertThat(stored).singleElement().satisfies(row -> {
            assertThat(row).doesNotContain(CARD).startsWith(fingerprinter.fingerprint(CARD));
        });
        mvc.perform(as("ANALYSTE", get("/api/v1/customers/" + JsonPath.<String>read(body, "$.id"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.firstName").value("Jeff"));
    }

    @Test
    void sameCardTwiceIs409() throws Exception {
        create("ADMIN", CARD, "Jeff").andExpect(status().isCreated());
        create("ADMIN", CARD, "Other").andExpect(status().isConflict())
                .andExpect(jsonPath("$.status").value(409));
    }

    @Test
    void invalidBodyIs400WithTheFields() throws Exception {
        mvc.perform(as("ADMIN", post("/api/v1/customers")).contentType(MediaType.APPLICATION_JSON)
                        .content(customerJson("12ab", "Jeff").replace("\"SC\"", "\"sc\"")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[*].field", hasItem("cardNumber")))
                .andExpect(jsonPath("$.errors[*].field", hasItem("state")));
    }

    @Test
    void updateChangesTheProfileButNotTheCard() throws Exception {
        String id = idOf(create("ADMIN", CARD, "Jeff"));

        mvc.perform(as("ADMIN", put("/api/v1/customers/" + id)).contentType(MediaType.APPLICATION_JSON)
                        .content(profileJson("Jeffrey")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.firstName").value("Jeffrey"))
                .andExpect(jsonPath("$.cardLast4").value("1966"));
        lookup("SIMULATEUR", CARD).andExpect(jsonPath("$.customerId").value(id));
    }

    @Test
    void unknownIdIs404() throws Exception {
        String unknown = "/api/v1/customers/00000000-0000-0000-0000-000000000000";
        mvc.perform(as("ADMIN", get(unknown))).andExpect(status().isNotFound());
        mvc.perform(as("ADMIN", put(unknown)).contentType(MediaType.APPLICATION_JSON).content(profileJson("X")))
                .andExpect(status().isNotFound());
    }

    // ---- list

    @Test
    void listFiltersAndPages() throws Exception {
        create("ADMIN", "4000000000000001", "Alice");
        create("ADMIN", "4000000000000002", "Bob");
        create("ADMIN", "4000000000000003", "Carla");

        mvc.perform(as("ANALYSTE", get("/api/v1/customers").param("name", "ALI")))
                .andExpect(jsonPath("$.content", hasSize(1)))
                .andExpect(jsonPath("$.content[0].firstName").value("Alice"));
        mvc.perform(as("ANALYSTE", get("/api/v1/customers").param("cardLast4", "0002")))
                .andExpect(jsonPath("$.content[0].firstName").value("Bob"));
        mvc.perform(as("ANALYSTE", get("/api/v1/customers").param("city", "columbia").param("state", "SC")))
                .andExpect(jsonPath("$.content", hasSize(3)));
        mvc.perform(as("ANALYSTE", get("/api/v1/customers").param("size", "2").param("sort", "firstName,desc")))
                .andExpect(jsonPath("$.content[0].firstName").value("Carla"))
                .andExpect(jsonPath("$.page.size").value(2))
                .andExpect(jsonPath("$.page.totalElements").value(3))
                .andExpect(jsonPath("$.page.totalPages").value(2));
        mvc.perform(as("ANALYSTE", get("/api/v1/customers").param("name", "%")))
                .andExpect(jsonPath("$.content", hasSize(0)));
    }

    @Test
    void unknownSortPropertyIs400() throws Exception {
        mvc.perform(as("ANALYSTE", get("/api/v1/customers").param("sort", "cardFingerprint")))
                .andExpect(status().isBadRequest());
    }

    // ---- internal endpoints

    @Test
    void lookupResolvesTheCardOr404() throws Exception {
        String id = idOf(create("ADMIN", CARD, "Jeff"));

        lookup("SIMULATEUR", CARD).andExpect(status().isOk())
                .andExpect(jsonPath("$.customerId").value(id))
                .andExpect(jsonPath("$.cardLast4").value("1966"));
        lookup("SIMULATEUR", "4999999999999999").andExpect(status().isNotFound());
        lookup("SIMULATEUR", "abc").andExpect(status().isBadRequest());
    }

    @Test
    void riskProfileHasExactlyTheModelFields() throws Exception {
        String id = idOf(create("ADMIN", CARD, "Jeff"));

        String body = mvc.perform(as("ANALYSTE", get("/internal/customers/" + id + "/risk-profile")))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        assertThat(JsonPath.<java.util.Map<String, Object>>read(body, "$"))
                .containsOnlyKeys("customerId", "dob", "gender", "cityPop", "lat", "long", "state")
                .containsEntry("dob", "1968-03-19")
                .containsEntry("state", "SC");
    }

    // ---- Sparkov seed (D50)

    @Test
    void seedLoadsEachSparkovCardOnceAndOnlyIntoAnEmptyTable(@TempDir Path dir) throws IOException {
        Path file = Files.writeString(dir.resolve("fraudTest.csv"), SparkovCustomerReaderTest.SPARKOV);
        CustomerSeeder seeder = new CustomerSeeder(new CustomerProperties("unused", file.toString()),
                customers, fingerprinter, jdbc, transaction);

        assertThat(seeder.seed()).isEqualTo(2);
        assertThat(customers.findByCardFingerprint(fingerprinter.fingerprint("60416207185")))
                .get().satisfies(c -> assertThat(c.getJob()).isEqualTo("Sales professional, IT"));
        assertThat(seeder.seed()).as("table not empty: skipped").isZero();
        assertThat(customers.count()).isEqualTo(2);

        assertThat(new CustomerSeeder(new CustomerProperties("unused", " "), customers, fingerprinter, jdbc,
                transaction).seed()).as("no path: skipped").isZero();
    }

    // ---- helpers

    private ResultActions create(String role, String card, String firstName) throws Exception {
        return mvc.perform(as(role, post("/api/v1/customers")).contentType(MediaType.APPLICATION_JSON)
                .content(customerJson(card, firstName)));
    }

    private ResultActions lookup(String role, String card) throws Exception {
        return mvc.perform(as(role, post("/internal/customers/lookup")).contentType(MediaType.APPLICATION_JSON)
                .content("{\"cardNumber\":\"" + card + "\"}"));
    }

    private static String idOf(ResultActions created) throws Exception {
        return JsonPath.read(created.andReturn().getResponse().getContentAsString(), "$.id");
    }

    private static MockHttpServletRequestBuilder as(String role, MockHttpServletRequestBuilder request) {
        return request.header(HttpHeaders.AUTHORIZATION, "Bearer " + role);
    }

    private static String customerJson(String card, String firstName) {
        return profileJson(firstName).replaceFirst("\\{", "{\"cardNumber\":\"" + card + "\",");
    }

    private static String profileJson(String firstName) {
        return """
                {"firstName":"%s","lastName":"Elliott","gender":"M","dob":"1968-03-19","job":"Mechanical engineer",
                 "street":"351 Darlene Green","city":"Columbia","state":"SC","zip":"29209","cityPop":333497,
                 "lat":33.9659,"long":-80.9355}""".formatted(firstName);
    }

    private static Jwt jwt(String role) {
        return Jwt.withTokenValue(role)
                .header("alg", "RS256")
                .subject("user-1")
                .claim("roles", List.of(role))
                .issuedAt(Instant.now())
                .expiresAt(Instant.now().plusSeconds(900))
                .build();
    }
}
