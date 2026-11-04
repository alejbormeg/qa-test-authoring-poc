using System.Collections.Concurrent;
using System.Text.Json;
using Microsoft.Playwright;

namespace QaWeb.Tests.Support;

/// <summary>Una entrada de Mappings/&lt;pagina&gt;.json.</summary>
public sealed record ComponentDefinition(string Selector, string Tipo, string Descripcion);

/// <summary>
/// Acceso a los componentes mapeados. Los tests nunca usan selectores directamente:
/// <c>Components.Component(Page, "login.usuario")</c>.
/// </summary>
public static class Components
{
    private static readonly ConcurrentDictionary<string, IReadOnlyDictionary<string, ComponentDefinition>> Cache = new();
    private static readonly JsonSerializerOptions Json = new() { PropertyNameCaseInsensitive = true };

    private static string MappingsDir => Path.Combine(AppContext.BaseDirectory, "Mappings");

    public static IReadOnlyDictionary<string, ComponentDefinition> Mapping(string pagina) =>
        Cache.GetOrAdd(pagina, p =>
        {
            var file = Path.Combine(MappingsDir, $"{p}.json");
            if (!File.Exists(file)) throw new InvalidOperationException($"No existe el mapeo de la página '{p}' ({file})");
            return JsonSerializer.Deserialize<Dictionary<string, ComponentDefinition>>(File.ReadAllText(file), Json)!;
        });

    public static ILocator Component(IPage page, string referencia)
    {
        var partes = referencia.Split('.', 2);
        if (partes.Length != 2) throw new ArgumentException($"Referencia '{referencia}' no válida: usa 'pagina.componente'");
        if (!Mapping(partes[0]).TryGetValue(partes[1], out var def))
            throw new InvalidOperationException($"El componente '{referencia}' no está mapeado");
        return page.Locator(def.Selector);
    }

    public static async Task GoToAsync(IPage page, string pagina, string query = "")
    {
        var rutas = JsonSerializer.Deserialize<Dictionary<string, string>>(
            File.ReadAllText(Path.Combine(MappingsDir, "_rutas.json")))!;
        if (!rutas.TryGetValue(pagina, out var ruta)) throw new InvalidOperationException($"No hay ruta para la página '{pagina}'");
        await page.GotoAsync(ruta + query);
    }
}
