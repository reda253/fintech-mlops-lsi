package ma.fintech.customer.service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;

import ma.fintech.customer.domain.Customer;
import ma.fintech.customer.domain.Gender;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

public class SparkovCustomerReaderTest {

    /** Real Sparkov header and the shapes that matter: quoted fields with commas, an 11-digit card. */
    public static final String SPARKOV = """
            ,trans_date_trans_time,cc_num,merchant,category,amt,first,last,gender,street,city,state,zip,lat,long,city_pop,job,dob,trans_num,unix_time,merch_lat,merch_long,is_fraud
            0,2020-06-21 12:14:25,2291163933867244,fraud_Kirlin and Sons,personal_care,2.86,Jeff,Elliott,M,351 Darlene Green,Columbia,SC,29209,33.9659,-80.9355,333497,Mechanical engineer,1968-03-19,2da90c7d74bd46a0caf3777415b3ebd3,1371816865,33.986391,-81.200714,0
            1,2020-06-21 12:14:33,60416207185,"fraud_Sporer-Keebler",personal_care,29.84,Joanne,Williams,F,3638 Marsh Union,Altonah,UT,84002,40.3207,-110.436,302,"Sales professional, IT",1990-01-17,324cc204407e99f51b0d6ca0055005e7,1371816873,39.450498,-109.960431,1
            2,2020-06-21 12:14:53,2291163933867244,fraud_Lind-Buckridge,health_fitness,41.28,Jeff,Elliott,M,351 Darlene Green,Columbia,SC,29209,33.9659,-80.9355,333497,Mechanical engineer,1968-03-19,c81755dbbbea9d5c77f094348a7579be,1371816893,32.575873,-80.744594,0
            """;

    @Test
    void oneCustomerPerCardWithQuotedFields(@TempDir Path dir) throws IOException {
        Path file = Files.writeString(dir.resolve("fraudTest.csv"), SPARKOV);

        Map<String, Customer.Profile> byCard = SparkovCustomerReader.read(List.of(file));

        assertThat(byCard).containsOnlyKeys("2291163933867244", "60416207185");
        Customer.Profile joanne = byCard.get("60416207185");
        assertThat(joanne.job()).isEqualTo("Sales professional, IT");
        assertThat(joanne.gender()).isEqualTo(Gender.F);
        assertThat(joanne.dob()).isEqualTo(LocalDate.of(1990, 1, 17));
        assertThat(joanne.state()).isEqualTo("UT");
        assertThat(joanne.cityPop()).isEqualTo(302);
        assertThat(joanne.latitude()).isEqualTo(40.3207);
        assertThat(joanne.longitude()).isEqualTo(-110.436);
    }

    @Test
    void severalFilesAreMergedFirstOccurrenceWins(@TempDir Path dir) throws IOException {
        Path test = Files.writeString(dir.resolve("fraudTest.csv"), SPARKOV);
        Path train = Files.writeString(dir.resolve("fraudTrain.csv"), SPARKOV.replace("Joanne", "Jo"));

        assertThat(SparkovCustomerReader.read(List.of(test, train)).get("60416207185").firstName())
                .isEqualTo("Joanne");
    }

    @Test
    void aFileWithoutTheSparkovColumnsIsRejected(@TempDir Path dir) throws IOException {
        Path file = Files.writeString(dir.resolve("other.csv"), "a,b,c\n1,2,3\n");

        assertThatThrownBy(() -> SparkovCustomerReader.read(List.of(file)))
                .hasMessageContaining("not a Sparkov file");
    }

    @Test
    void escapedQuotes() {
        assertThat(SparkovCustomerReader.parseLine("a,\"say \"\"hi\"\", ok\",c"))
                .containsExactly("a", "say \"hi\", ok", "c");
    }
}
