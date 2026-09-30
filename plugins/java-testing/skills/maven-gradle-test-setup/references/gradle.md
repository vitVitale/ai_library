# Gradle test configuration (Kotlin DSL)

Prefer the version catalog (`gradle/libs.versions.toml`) if the project has one. Use versions already there, or the latest stable release.

## Unit tests + separate integration test suite (JVM Test Suite plugin)
```kotlin
plugins {
    java
    jacoco
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:${junitVersion}"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
    testImplementation("org.assertj:assertj-core:${assertjVersion}")
    testImplementation("org.mockito:mockito-junit-jupiter:${mockitoVersion}")
}

testing {
    suites {
        val test by getting(JvmTestSuite::class) {
            useJUnitJupiter()
        }
        register<JvmTestSuite>("integrationTest") {
            useJUnitJupiter()
            dependencies {
                implementation(project())
                implementation("org.assertj:assertj-core:${assertjVersion}")
            }
            targets.all {
                testTask.configure { shouldRunAfter(test) }
            }
        }
    }
}

tasks.named("check") { dependsOn(testing.suites.named("integrationTest")) }
```
Integration tests then live in `src/integrationTest/java` and run with `./gradlew integrationTest`.

## Tag filtering from the command line
```kotlin
tasks.withType<Test>().configureEach {
    useJUnitPlatform {
        (findProperty("includeTags") as String?)?.let { includeTags(*it.split(",").toTypedArray()) }
        (findProperty("excludeTags") as String?)?.let { excludeTags(*it.split(",").toTypedArray()) }
    }
    testLogging {
        events("failed", "skipped")
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
    }
    // forward -Dapi.* and -Dui.* from the gradlew command line into the test JVM
    System.getProperties().forEach { (key, value) ->
        val name = key.toString()
        if (name.startsWith("api.") || name.startsWith("ui.")) systemProperty(name, value)
    }
}
```
Run: `./gradlew test -PincludeTags=smoke -PexcludeTags=slow`.

Pass config to tests with `./gradlew test -Dapi.baseUrl=...`.

## Allure
Use the `io.qameta.allure` Gradle plugin (it configures AspectJ and results dir):
```kotlin
plugins { id("io.qameta.allure") version "<latest>" }
allure {
    adapter { frameworks { junit5 } }
}
```
Report: `./gradlew allureServe` or `allureReport`.

## JaCoCo
```kotlin
tasks.jacocoTestReport {
    dependsOn(tasks.test)
    reports { xml.required = true; html.required = true }
}
```

## Retry (temporary, report it)
`org.gradle.test-retry` plugin: `tasks.test { retry { maxRetries = 2; failOnPassedAfterRetry = false } }`.
