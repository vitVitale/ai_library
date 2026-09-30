package com.example.ui.pages;

import static com.codeborne.selenide.Condition.text;
import static com.codeborne.selenide.Condition.visible;
import static com.codeborne.selenide.Selenide.$;
import static com.codeborne.selenide.Selenide.open;

import com.codeborne.selenide.SelenideElement;

/** Page object: locators are private, methods are user actions returning the next page. */
public class LoginPage {

    private final SelenideElement email = $("[data-testid=login-email]");
    private final SelenideElement password = $("[data-testid=login-password]");
    private final SelenideElement submit = $("[data-testid=login-submit]");
    private final SelenideElement error = $("[data-testid=login-error]");

    public static LoginPage openPage() {
        open("/login");   // relative to Configuration.baseUrl / -Dselenide.baseUrl
        return new LoginPage();
    }

    public DashboardPage loginAs(String user, String pass) {
        email.setValue(user);
        password.setValue(pass);
        submit.click();
        return new DashboardPage();
    }

    public LoginPage loginExpectingError(String user, String pass) {
        email.setValue(user);
        password.setValue(pass);
        submit.click();
        error.shouldBe(visible);
        return this;
    }

    public LoginPage shouldShowError(String message) {
        error.shouldHave(text(message));
        return this;
    }
}

/*
Usage in a test:

    @Test
    void showsErrorForWrongPassword() {
        LoginPage.openPage()
            .loginExpectingError("ann@example.com", "wrong")
            .shouldShowError("Invalid email or password");
    }
*/
