# QaWeb.Tests

Tests end-to-end de la tienda web con Playwright para .NET y xUnit.

## Convenciones del equipo

- Los componentes de cada página se mapean en `Mappings/<pagina>.json` (`selector`, `tipo`, `descripcion`). Los tests no usan selectores directamente: siempre `Components.Component(Page, "pagina.componente")`.
- `Mappings/_rutas.json` contiene las rutas de cada página. Se navega con `Components.GoToAsync(Page, "pagina")`.
- Las acciones de negocio que se repiten van en `Pages/` (page objects).
- Una clase de tests por funcionalidad. Cada método se llama `<ID_DEL_CASO>_<DescripcionEnPascalCase>` y lleva `[Trait("Feature", "<id de la Feature en Azure DevOps>")]`.
- El nombre completo del método (`QaWeb.Tests.<Clase>.<Metodo>`) es el `AutomatedTestName` del Test Case en Azure Test Plans.

## Ejecutar

```bash
dotnet test --settings .runsettings
```
