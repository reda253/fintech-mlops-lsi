package ma.fintech.customer.service;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import ma.fintech.customer.domain.Customer;
import ma.fintech.customer.domain.Gender;

/**
 * Extracts the distinct cardholders of raw Sparkov CSV files (one customer per {@code cc_num}).
 * Only the customer columns are read; {@code is_fraud} and every transaction column are ignored,
 * so the seed never touches labels (D50).
 */
public final class SparkovCustomerReader {

    static final List<String> COLUMNS = List.of("cc_num", "first", "last", "gender", "street", "city",
            "state", "zip", "lat", "long", "city_pop", "job", "dob");

    private SparkovCustomerReader() {
    }

    /** Card number → profile, first occurrence wins, in file order. */
    public static Map<String, Customer.Profile> read(List<Path> files) {
        Map<String, Customer.Profile> byCard = new LinkedHashMap<>();
        for (Path file : files) {
            try (BufferedReader reader = Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                String header = reader.readLine();
                if (header == null) {
                    continue;
                }
                int[] index = indexes(parseLine(header), file);
                String line;
                while ((line = reader.readLine()) != null) {
                    if (line.isBlank()) {
                        continue;
                    }
                    List<String> fields = parseLine(line);
                    String card = fields.get(index[0]);
                    if (!byCard.containsKey(card)) {
                        byCard.put(card, profile(fields, index));
                    }
                }
            } catch (IOException e) {
                throw new UncheckedIOException("Cannot read Sparkov file " + file, e);
            }
        }
        return byCard;
    }

    private static int[] indexes(List<String> header, Path file) {
        int[] index = new int[COLUMNS.size()];
        for (int i = 0; i < COLUMNS.size(); i++) {
            index[i] = header.indexOf(COLUMNS.get(i));
            if (index[i] < 0) {
                throw new IllegalArgumentException(file + " is not a Sparkov file: no column " + COLUMNS.get(i));
            }
        }
        return index;
    }

    private static Customer.Profile profile(List<String> f, int[] i) {
        return new Customer.Profile(f.get(i[1]), f.get(i[2]), Gender.valueOf(f.get(i[3])),
                LocalDate.parse(f.get(i[12])), f.get(i[11]), f.get(i[4]), f.get(i[5]), f.get(i[6]),
                f.get(i[7]), Integer.parseInt(f.get(i[10])), Double.parseDouble(f.get(i[8])),
                Double.parseDouble(f.get(i[9])));
    }

    /** RFC 4180 fields: commas inside double quotes, {@code ""} for a literal quote. */
    static List<String> parseLine(String line) {
        List<String> fields = new ArrayList<>();
        StringBuilder current = new StringBuilder();
        boolean quoted = false;
        for (int i = 0; i < line.length(); i++) {
            char c = line.charAt(i);
            if (quoted) {
                if (c == '"' && i + 1 < line.length() && line.charAt(i + 1) == '"') {
                    current.append('"');
                    i++;
                } else if (c == '"') {
                    quoted = false;
                } else {
                    current.append(c);
                }
            } else if (c == '"') {
                quoted = true;
            } else if (c == ',') {
                fields.add(current.toString());
                current.setLength(0);
            } else {
                current.append(c);
            }
        }
        fields.add(current.toString());
        return fields;
    }
}
