# Requisitos y dónde se ven

Lo que tiene que cumplir el asistente y dónde está resuelto en la PoC.

| Requisito | En la PoC |
|---|---|
| El input es un DFF con los casos a probar | Subida de `.docx` (tabla o prosa), `.md` o `.txt` · `adapters/dff.py`, `llm/*` |
| QA revisa y aprueba los casos extraídos | Gate 1 · edición de cada caso, avisos, duplicados contra Azure · `ui/run_page.py` (`gate1`) |
| Tests en Playwright siguiendo sus convenciones y mapeos | C# + Playwright .NET + xUnit; `Components.Component(Page, "pagina.componente")`, page objects · `pipeline/toolbox.py` |
| Si falta un componente, se propone aparte; no se inventan selectores | `proponer_componente` valida contra el DOM real; aparece en «Mapeos nuevos» y en la PR |
| Ejecución de prueba con el resultado adjunto | `dotnet test` contra la web, resultado del TRX por caso · `adapters/dotnet_runner.py` |
| Revisión del código en una pull request | Gate 2 en el asistente + PR en Azure Repos con política de aprobación · consola `/console/prs` |
| Registro en la Feature y en el Test Plan por versión o funcionalidad | Gate 3 · Test Case con relación `Tests` a la Feature, pasos, automatización asociada y suite · `service._register` |
| Nada llega al repo ni a Azure sin aprobación de QA | Los gates se aplican en el servicio, no solo en la UI · `tests/test_extraction_and_rules.py` |
| Estado por caso y poder retomar | Estados persistidos, reintento idempotente, inyección de fallos · consola `/console/faults` |
| Informe de cierre: tiempo, aceptados sin cambios, mapeos reutilizados y nuevos | Dashboard · `ui/dashboard.py` |
| Restricciones sobre el modelo de IA | Adaptador conmutable (`QA_AI`); la IA va detrás de un puerto (`extract`/`generate`) |

Fuera de la PoC: Appium para móvil (el toolbox y el registro son los mismos; cambian el runner y el inspector), otros formatos de mapeo (aislados en `Workspace.mapping`/`format_mapping`) y la conexión a un Azure DevOps real (`AZURE_BASE_URL`, `AZURE_PAT`).
