using Microsoft.Playwright;
using Microsoft.Playwright.Xunit;

namespace QaWeb.Tests.Support;

/// <summary>Base de todos los tests: navegador limpio por test y URL base del entorno.</summary>
public abstract class BaseTest : PageTest
{
    public static string BaseUrl =>
        Environment.GetEnvironmentVariable("BASE_URL")?.TrimEnd('/') ?? "http://localhost:8602";

    public override BrowserNewContextOptions ContextOptions() => new()
    {
        BaseURL = BaseUrl,
        Locale = "es-ES",
        ViewportSize = new() { Width = 1280, Height = 800 },
    };
}
