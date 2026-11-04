using Microsoft.Playwright;
using QaWeb.Tests.Support;

namespace QaWeb.Tests.Pages;

public sealed class LoginPage(IPage page)
{
    public const string UsuarioDemo = "demo@tienda.test";
    public const string PasswordDemo = "Demo1234";

    public async Task LoginAsync(string usuario, string password)
    {
        await Components.GoToAsync(page, "login");
        await Components.Component(page, "login.usuario").FillAsync(usuario);
        await Components.Component(page, "login.password").FillAsync(password);
        await Components.Component(page, "login.entrar").ClickAsync();
    }

    public Task LoginComoDemoAsync() => LoginAsync(UsuarioDemo, PasswordDemo);
}
