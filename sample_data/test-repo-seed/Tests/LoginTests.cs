using QaWeb.Tests.Pages;
using QaWeb.Tests.Support;
using static QaWeb.Tests.Support.Components;

namespace QaWeb.Tests;

public class LoginTests : BaseTest
{
    [Fact]
    [Trait("Feature", "101")]
    public async Task TC_LOGIN_001_LoginCorrecto()
    {
        await new LoginPage(Page).LoginComoDemoAsync();

        await Expect(Component(Page, "cabecera.usuario")).ToContainTextAsync("Lucía Martín");
        await Expect(Component(Page, "perfil.email")).ToHaveTextAsync(LoginPage.UsuarioDemo);
    }

    [Fact]
    [Trait("Feature", "101")]
    public async Task TC_LOGIN_002_PasswordIncorrecta()
    {
        await new LoginPage(Page).LoginAsync(LoginPage.UsuarioDemo, "incorrecta");

        await Expect(Component(Page, "login.error")).ToContainTextAsync("Usuario o contraseña incorrectos");
    }
}
