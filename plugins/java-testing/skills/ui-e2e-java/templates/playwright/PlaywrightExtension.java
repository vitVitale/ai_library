package com.example.ui.support;

import com.microsoft.playwright.Browser;
import com.microsoft.playwright.BrowserContext;
import com.microsoft.playwright.BrowserType;
import com.microsoft.playwright.Page;
import com.microsoft.playwright.Playwright;
import com.microsoft.playwright.Tracing;
import java.nio.file.Path;
import org.junit.jupiter.api.extension.AfterEachCallback;
import org.junit.jupiter.api.extension.BeforeEachCallback;
import org.junit.jupiter.api.extension.ExtensionContext;
import org.junit.jupiter.api.extension.ParameterContext;
import org.junit.jupiter.api.extension.ParameterResolver;

/**
 * One browser per test class thread, one fresh context per test, trace saved only on failure.
 * Usage: {@code @ExtendWith(PlaywrightExtension.class)} and a {@code Page page} test method parameter.
 * Config: -Dui.baseUrl=..., -Dui.headless=false to watch locally.
 */
public class PlaywrightExtension implements BeforeEachCallback, AfterEachCallback, ParameterResolver {

    private static final ThreadLocal<Playwright> PLAYWRIGHT = ThreadLocal.withInitial(Playwright::create);
    private static final ThreadLocal<Browser> BROWSER = ThreadLocal.withInitial(() ->
        PLAYWRIGHT.get().chromium().launch(new BrowserType.LaunchOptions()
            .setHeadless(Boolean.parseBoolean(System.getProperty("ui.headless", "true")))));

    private static final ExtensionContext.Namespace NS = ExtensionContext.Namespace.create(PlaywrightExtension.class);

    @Override
    public void beforeEach(ExtensionContext ctx) {
        BrowserContext context = BROWSER.get().newContext(new Browser.NewContextOptions()
            .setBaseURL(System.getProperty("ui.baseUrl", "http://localhost:3000"))
            .setViewportSize(1440, 900));
        context.tracing().start(new Tracing.StartOptions().setScreenshots(true).setSnapshots(true).setSources(true));
        ctx.getStore(NS).put("context", context);
        ctx.getStore(NS).put("page", context.newPage());
    }

    @Override
    public void afterEach(ExtensionContext ctx) {
        BrowserContext context = ctx.getStore(NS).remove("context", BrowserContext.class);
        if (context == null) {
            return;
        }
        if (ctx.getExecutionException().isPresent()) {
            Path trace = Path.of("build", "playwright-traces", ctx.getDisplayName().replaceAll("\\W+", "_") + ".zip");
            context.tracing().stop(new Tracing.StopOptions().setPath(trace));  // open with: npx playwright show-trace <zip>
        } else {
            context.tracing().stop();
        }
        context.close();
    }

    @Override
    public boolean supportsParameter(ParameterContext param, ExtensionContext ctx) {
        return param.getParameter().getType() == Page.class;
    }

    @Override
    public Object resolveParameter(ParameterContext param, ExtensionContext ctx) {
        return ctx.getStore(NS).get("page", Page.class);
    }
}
