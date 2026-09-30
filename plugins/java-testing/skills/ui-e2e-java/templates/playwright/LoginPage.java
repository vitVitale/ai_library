package com.example.ui.pages;

import static com.microsoft.playwright.assertions.PlaywrightAssertions.assertThat;

import com.microsoft.playwright.Locator;
import com.microsoft.playwright.Page;

/** Page object for Playwright: locators built once from the page, actions return the next page. */
public class LoginPage {

    private final Page page;
    private final Locator email;
    private final Locator password;
    private final Locator submit;
    private final Locator error;

    public LoginPage(Page page) {
        this.page = page;
        this.email = page.getByTestId("login-email");
        this.password = page.getByTestId("login-password");
        this.submit = page.getByTestId("login-submit");
        this.error = page.getByTestId("login-error");
    }

    public LoginPage open() {
        page.navigate("/login");   // relative to BrowserContext baseURL
        return this;
    }

    public DashboardPage loginAs(String user, String pass) {
        email.fill(user);
        password.fill(pass);
        page.waitForResponse(r -> r.url().endsWith("/api/session") && r.ok(), submit::click);
        return new DashboardPage(page);
    }

    public LoginPage loginExpectingError(String user, String pass) {
        email.fill(user);
        password.fill(pass);
        submit.click();
        return this;
    }

    public LoginPage shouldShowError(String message) {
        assertThat(error).hasText(message);
        return this;
    }
}
