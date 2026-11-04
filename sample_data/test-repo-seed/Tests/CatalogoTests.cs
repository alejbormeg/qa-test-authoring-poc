using QaWeb.Tests.Support;
using static QaWeb.Tests.Support.Components;

namespace QaWeb.Tests;

public class CatalogoTests : BaseTest
{
    [Fact]
    [Trait("Feature", "102")]
    public async Task TC_CAT_001_BuscarProductoPorNombre()
    {
        await GoToAsync(Page, "catalogo");
        await Component(Page, "cabecera.buscador").FillAsync("teclado");
        await Component(Page, "cabecera.buscar").ClickAsync();

        await Expect(Component(Page, "catalogo.productos")).ToHaveCountAsync(1);
        await Expect(Component(Page, "catalogo.nombre_producto")).ToContainTextAsync("Teclado mecánico");
    }

    [Fact]
    [Trait("Feature", "102")]
    public async Task TC_CAT_002_BusquedaSinResultados()
    {
        await GoToAsync(Page, "catalogo", "?q=bicicleta");

        await Expect(Component(Page, "catalogo.sin_resultados")).ToBeVisibleAsync();
    }
}
