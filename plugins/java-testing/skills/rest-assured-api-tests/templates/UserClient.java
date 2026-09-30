package com.example.api.clients;

import static io.restassured.RestAssured.given;

import com.example.api.models.User;
import com.example.api.specs.Specs;
import io.restassured.response.Response;

/** One client per resource. Returns raw Response so tests can assert negative cases too. */
public class UserClient {

    public Response create(User user) {
        return given().spec(Specs.request())
            .body(user)
            .when().post("/users")
            .then().log().ifValidationFails()
            .extract().response();
    }

    public Response get(long id) {
        return given().spec(Specs.request())
            .pathParam("id", id)
            .when().get("/users/{id}")
            .then().log().ifValidationFails()
            .extract().response();
    }

    public Response delete(long id) {
        return given().spec(Specs.request())
            .pathParam("id", id)
            .when().delete("/users/{id}")
            .then().log().ifValidationFails()
            .extract().response();
    }
}
