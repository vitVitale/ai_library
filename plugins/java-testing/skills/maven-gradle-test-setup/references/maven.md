# Maven test configuration

Replace `${...}` properties with versions already in the project, or the latest stable release from Maven Central.

## Dependencies (BOM + test deps)
```xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.junit</groupId>
      <artifactId>junit-bom</artifactId>
      <version>${junit.version}</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.assertj</groupId>
    <artifactId>assertj-core</artifactId>
    <version>${assertj.version}</version>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.mockito</groupId>
    <artifactId>mockito-junit-jupiter</artifactId>
    <version>${mockito.version}</version>
    <scope>test</scope>
  </dependency>
</dependencies>
```

## Surefire (unit) + Failsafe (integration)
```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <version>${surefire.version}</version>
      <configuration>
        <excludedGroups>integration</excludedGroups>
      </configuration>
    </plugin>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-failsafe-plugin</artifactId>
      <version>${surefire.version}</version>   <!-- same version as surefire -->
      <executions>
        <execution>
          <goals>
            <goal>integration-test</goal>
            <goal>verify</goal>
          </goals>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
```
Failsafe picks up `**/*IT.java`, `**/IT*.java`, `**/*ITCase.java` during `mvn verify`.

Tag filtering from the CLI: `./mvnw test -Dgroups='smoke & !slow'` (JUnit tag expressions).

Retry flaky tests (temporary, report it): `-Dsurefire.rerunFailingTestsCount=2`.

## Allure
```xml
<dependency>
  <groupId>io.qameta.allure</groupId>
  <artifactId>allure-junit5</artifactId>
  <version>${allure.version}</version>
  <scope>test</scope>
</dependency>
<!-- optional: io.qameta.allure:allure-rest-assured, io.qameta.allure:allure-selenide -->
```
For `@Step` / `@Attachment` add AspectJ weaving to Surefire:
```xml
<configuration>
  <argLine>-javaagent:"${settings.localRepository}/org/aspectj/aspectjweaver/${aspectj.version}/aspectjweaver-${aspectj.version}.jar"</argLine>
  <systemPropertyVariables>
    <allure.results.directory>${project.build.directory}/allure-results</allure.results.directory>
  </systemPropertyVariables>
</configuration>
```
(and declare `org.aspectj:aspectjweaver` as a plugin dependency). Generate the report with `allure serve target/allure-results` or the `io.qameta.allure:allure-maven` plugin.

## JaCoCo coverage
```xml
<plugin>
  <groupId>org.jacoco</groupId>
  <artifactId>jacoco-maven-plugin</artifactId>
  <version>${jacoco.version}</version>
  <executions>
    <execution><goals><goal>prepare-agent</goal></goals></execution>
    <execution><id>report</id><phase>verify</phase><goals><goal>report</goal></goals></execution>
  </executions>
</plugin>
```
If Surefire has its own `<argLine>`, prepend `@{argLine}` so the JaCoCo agent is not lost.
