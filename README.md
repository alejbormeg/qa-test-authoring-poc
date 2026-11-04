# qa-test-authoring-poc

Prueba de concepto de un **asistente de QA** que convierte un documento funcional con casos de prueba (DFF) en tests end-to-end en **C# con Playwright para .NET y xUnit**, los ejecuta contra la web, abre la **pull request** y los registra en **Azure Test Plans**. Nada avanza sin la aprobación de una persona de QA.

```
DFF (.docx) ──► casos extraídos ──[Gate 1: QA aprueba/edita]──► tests C# generados y ejecutados
            ──[Gate 2: QA revisa código y resultados]──► PR en Azure Repos (revisión y merge del equipo)
            ──[Gate 3: QA confirma dónde se registran]──► Test Cases en la Feature + suite del Test Plan
```

Todo funciona en local. La IA puede ser real (Claude) o simulada, y el resto se simula de forma creíble:

| Pieza | En la PoC | En el cliente |
|---|---|---|
| Web bajo prueba | `mocks/demo_site`: tienda demo con `data-testid` (:8602) | Sus webs |
| Repositorio de tests | Solución .NET 8 + `Microsoft.Playwright.Xunit` con mapeos JSON por página, page objects y tests de ejemplo (`sample_data/test-repo-seed`), publicada en un repo git local que hace de Azure Repos | Sus proyectos de test |
| Azure DevOps | `mocks/azure_devops`: subconjunto **compatible de la REST 7.1** (work items con JSON Patch, WIQL, Test Plans/suites, pull requests con votos y merge real) + consola web (:8601/console) | `dev.azure.com`, cambiando `AZURE_BASE_URL` y `AZURE_PAT` |
| IA | `QA_AI=mock` (por defecto sin clave) o `QA_AI=claude` (`claude-opus-5-5`) | El modelo que se acuerde |

## Requisitos

- Python 3.12 y [uv](https://docs.astral.sh/uv/).
- SDK de **.NET 8**. Sin permisos de administrador basta con instalarlo solo para el usuario (`~/.dotnet`, se detecta solo):
  `curl -sSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 8.0`.
- Git.

## Arranque

```bash
make setup     # dependencias, chromium de Playwright y paquetes NuGet
make seed      # estado inicial: repo de tests, Features, casos existentes y Test Plans
make up        # asistente :8600 · Azure DevOps simulado :8601/console · web :8602
```

Abre http://localhost:8600, pulsa **Nueva ejecución**, elige un DFF de ejemplo y sigue el flujo. La revisión y el merge de la PR se hacen en la consola de Azure DevOps simulada, como en el día a día del equipo; el asistente detecta el merge y pasa al registro.

Con IA real: copia `.env.example` a `.env`, pon `ANTHROPIC_API_KEY` y `QA_AI=claude`, y reinicia.

## Qué enseña

- **Extracción** de casos en tabla o en prosa, con avisos para QA (resultado esperado ausente, pasos vagos, datos contradictorios) y detección de casos que ya existen en Azure.
- **Generación que respeta las convenciones del equipo**: reutiliza los componentes mapeados y los page objects. Si falta un componente, lo busca en el **DOM real** y lo propone para el mapeo; un selector que no existe en la página se rechaza. El código no se acepta si no compila o si usa selectores directos.
- **Ejecución real** con `dotnet test` contra la web, con el resultado leído del TRX. Con IA real, los tests que fallan vuelven al modelo con el error real (hasta `QA_MAX_FIX_ATTEMPTS` intentos).
- **Revisión por QA** con editor de C#, diff entre la versión de la IA y la de QA, y opción de sacar casos de la PR.
- **Registro trazable**: cada Test Case se crea dentro de la Feature (`Tests`), con sus pasos, `AutomatedTestName = QaWeb.Tests.Generated.<Clase>.<Método>`, `AutomatedTestStorage = QaWeb.Tests.dll` y `AutomationStatus = Automated`, y se añade a la suite por versión o por funcionalidad.
- **Recuperación**: cada fase deja estado en SQLite. Un fallo (por ejemplo, Azure devolviendo 503 o un PAT caducado, que se inyectan desde la consola) deja la ejecución en error y el reintento sigue sin perder ni duplicar casos.
- **Auditoría y medición**: cada decisión guarda quién y cuándo. El dashboard muestra los tiempos por fase (asistente frente a QA), los tests en verde a la primera, los aceptados sin cambios, la reutilización de mapeos y el coste de IA por test.

## Comandos útiles

```bash
make test          # tests unitarios y de contrato (levantan su propio Azure simulado)
make demo-e2e      # recorre el flujo entero sin UI y comprueba Azure (con `make up` en marcha)
make screenshots   # capturas de las pantallas en docs/capturas
make dff           # regenera los DFF de ejemplo
```

## Estructura

```
src/qa_assistant/   asistente: config, dominio, adaptadores (Azure, git, dotnet, DOM, DFF), IA (mock/Claude), flujo y UI
mocks/              web bajo prueba y Azure DevOps simulado
sample_data/        DFF de ejemplo y proyecto de tests semilla
scripts/            seed, recorrido e2e y capturas
docs/               arquitectura, guion de la demo y trazabilidad con la propuesta
```
