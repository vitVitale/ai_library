package com.example.api.specs;

import static org.hamcrest.Matchers.lessThan;

import io.restassured.builder.RequestSpecBuilder;
import io.restassured.builder.ResponseSpecBuilder;
import io.restassured.filter.log.LogDetail;
import io.restassured.http.ContentType;
import io.restassured.specification.RequestSpecification;
import io.restassured.specification.ResponseSpecification;

/** Shared specs. Config comes from -Dapi.baseUrl=... or API_BASE_URL. */
public final class Specs {

    private static final String BASE_URL =
        System.getProperty("api.baseUrl", System.getenv().getOrDefault("API_BASE_URL", "http://localhost:8080"));

    private Specs() {
    }

    public static RequestSpecification request() {
        return new RequestSpecBuilder()
            .setBaseUri(BASE_URL)
            .setBasePath("/api/v1")
            .setContentType(ContentType.JSON)
            .setAccept(ContentType.JSON)
            // .addFilter(new io.qameta.allure.restassured.AllureRestAssured())  // if Allure is used
            .log(LogDetail.URI)
            .build();
    }

    public static ResponseSpecification ok() {
        return new ResponseSpecBuilder()
            .expectStatusCode(200)
            .expectContentType(ContentType.JSON)
            .expectResponseTime(lessThan(2000L))
            .build();
    }
}
