using QaWeb.Tests.Pages;
using QaWeb.Tests.Support;
using static QaWeb.Tests.Support.Components;

namespace QaWeb.Tests;

public class CarritoTests : BaseTest
{
    [Fact]
    [Trait("Feature", "103")]
    public async Task TC_CARRITO_001_AnadirProductoAlCarrito()
    {
        await new CarritoPage(Page).AnadirProductoAsync(productoId: 1);

        await Expect(Component(Page, "producto.mensaje")).ToContainTextAsync("Producto añadido al carrito");
        await Expect(Component(Page, "cabecera.contador_carrito")).ToHaveTextAsync("1");
    }
}
