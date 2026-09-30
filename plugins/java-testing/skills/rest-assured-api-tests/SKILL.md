---
name: rest-assured-api-tests
description: Build REST API test suites in Java with RestAssured - shared request/response specs, config from environment, POJO (de)serialization, JSON schema validation, auth, logging on failure, Allure reporting and test data cleanup. Use when writing or refactoring HTTP/REST API tests in Java, adding API test coverage for an endpoint, or setting up an API test framework.
---

# RestAssured API tests

## Framework layout (create only what is missing)
```
src/test/java/<pkg>/api/
├── config/ApiConfig.java        # base URI, credentials from env/system props — never hardcoded secrets
├── specs/Specs.java             # shared RequestSpecification / ResponseSpecification
├── clients/UserClient.java      # one class per resource: methods return Response or DTOs
├── models/User.java             # request/response DTOs (records or Lombok)
├── data/UserFactory.java        # test data builders (unique values: UUID/timestamp suffix)
└── tests/UserApiTest.java       # tests only call clients + assert
src/test/resources/schemas/user.json
```
Templates: [templates/Specs.java](templates/Specs.java), [templates/UserClient.java](templates/UserClient.java), [templates/UserApiTest.java](templates/UserApiTest.java).

## Rules
- Tests read like specs: build data → call client → assert. No raw `given()` chains repeated in every test; put them in the client.
- Base URL and credentials come from `System.getProperty("api.baseUrl", System.getenv("API_BASE_URL"))`-style config so CI can target any environment.
- `.log().ifValidationFails()` on requests and responses; never log full bodies with secrets on success.
- Deserialize into DTOs (`.as(User.class)` / `.extract().as(...)`) and assert with AssertJ; use `body("path", matcher)` only for quick one-field checks.
- Validate the contract with `matchesJsonSchemaInClasspath("schemas/user.json")` (dependency `io.rest-assured:json-schema-validator`) for each endpoint at least once.
- Check status code **and** relevant headers (`Content-Type`, `Location` for 201) **and** body.
- Cover negative cases: 400 validation errors (assert error message/field), 401/403 auth, 404 unknown id, 409 conflicts. Use parameterized tests for validation matrices.
- Each test creates its own data and cleans up (`@AfterEach` delete via API, or unique data that can be left). No test depends on another test's data or order.
- Response time checks only as a loose guard: `.time(lessThan(2000L))`.
- If Allure is used, add `new AllureRestAssured()` as a filter in the request spec so requests/responses attach to the report.

## Common snippets
```java
// auth
given().spec(Specs.request()).auth().oauth2(token)
given().spec(Specs.request()).header("X-Api-Key", ApiConfig.apiKey())

// extract id for later calls
long id = client.create(user).then().statusCode(201).extract().jsonPath().getLong("id");

// generic list
List<User> users = client.list().then().statusCode(200).extract().as(new TypeRef<>() {});

// multipart
given().spec(Specs.request()).multiPart("file", new File("src/test/resources/files/a.pdf"), "application/pdf")
```

## Done checklist
- [ ] Runs against a configurable environment without code changes.
- [ ] Positive + negative + contract (schema) cases for each endpoint touched.
- [ ] No shared mutable state, safe to run in parallel.
