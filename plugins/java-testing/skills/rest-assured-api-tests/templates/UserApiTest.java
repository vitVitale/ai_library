package com.example.api.tests;

import static io.restassured.module.jsv.JsonSchemaValidator.matchesJsonSchemaInClasspath;
import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;

import com.example.api.clients.UserClient;
import com.example.api.data.UserFactory;
import com.example.api.models.ApiError;
import com.example.api.models.User;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

@Tag("api")
class UserApiTest {

    private final UserClient users = new UserClient();
    private final List<Long> createdIds = new ArrayList<>();

    @AfterEach
    void cleanUp() {
        createdIds.forEach(users::delete);
    }

    @Test
    void createsUser() {
        var request = UserFactory.valid();

        var response = users.create(request);

        response.then().statusCode(201)
            .header("Location", containsString("/users/"))
            .body(matchesJsonSchemaInClasspath("schemas/user.json"));
        var created = response.as(User.class);
        createdIds.add(created.id());
        assertThat(created).usingRecursiveComparison().ignoringFields("id").isEqualTo(request);
    }

    @ParameterizedTest(name = "{0} -> {1}")
    @CsvSource({
        "email, must be a valid email",
        "name,  must not be blank"
    })
    void rejectsInvalidField(String field, String expectedMessage) {
        var response = users.create(UserFactory.withInvalid(field));

        response.then().statusCode(400);
        var error = response.as(ApiError.class);
        assertThat(error.fieldErrors()).anySatisfy(e -> {
            assertThat(e.field()).isEqualTo(field);
            assertThat(e.message()).contains(expectedMessage);
        });
    }

    @Test
    void returns404ForUnknownUser() {
        users.get(Long.MAX_VALUE).then().statusCode(404);
    }
}
