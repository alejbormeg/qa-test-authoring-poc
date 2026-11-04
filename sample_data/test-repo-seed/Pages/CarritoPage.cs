using Microsoft.Playwright;
using QaWeb.Tests.Support;

namespace QaWeb.Tests.Pages;

public sealed class CarritoPage(IPage page)
{
    /// <summary>Abre la ficha del producto, lo añade y espera la confirmación.</summary>
    public async Task AnadirProductoAsync(int productoId, int cantidad = 1)
    {
        await Components.GoToAsync(page, "producto", $"?id={productoId}");
        await Components.Component(page, "producto.cantidad").FillAsync(cantidad.ToString());
        await Components.Component(page, "producto.anadir").ClickAsync();
        await Components.Component(page, "producto.mensaje").WaitForAsync();
    }
}
