# Guion de la demo (unos 20 minutos)

**Mensaje**: el asistente convierte el documento funcional en tests de Playwright en C# que siguen las convenciones del equipo y los deja registrados en Azure Test Plans. QA decide en tres puntos y nada llega al repositorio ni a Azure sin su aprobación.

Datos medidos con Claude (`claude-opus-5-5`) sobre los DFF de ejemplo:

| DFF | Casos | Extracción | Generación y ejecución | En verde a la primera | Coste de IA |
|---|---|---|---|---|---|
| Carrito y cupones (tabla) | 6, 1 duplicado | ~20 s | ~80 s | 5/5 | 0,40 $ (0,08 $ por test) |
| Checkout (prosa) | 3 | ~15 s | ~50 s | 3/3 | 0,21 $ (0,07 $ por test) |
| Área de cliente (borrador) | 3, todos con avisos | ~20 s | ~3 min (con autocorrección) | 1/3; los otros 2 los deja marcados como pendientes con el motivo | 0,58 $ |

## Preparación

**El día antes**

1. `.env` con `ANTHROPIC_API_KEY` y `QA_AI=auto` (o `claude`).
2. `make seed && make up` y un recorrido completo de prueba (`make demo-e2e`) para comprobar la clave, .NET y Playwright.

**30 minutos antes**

1. Estado limpio: `pkill -f honcho`, después `make seed && make up`.
2. Una ejecución ya terminada para tener datos en el dashboard y un plan B:
   `uv run python scripts/demo_e2e.py sample_data/dff/DFF_Checkout_v2.4.docx` (unos 2 minutos, 0,20 $).
   No uses el DFF del carrito: es el que se hace en directo y sus casos saldrían como duplicados.
3. Tres pestañas: asistente (http://localhost:8600), Azure DevOps simulado (http://localhost:8601/console) y la tienda (http://localhost:8602).
4. En la cabecera del asistente, la insignia de la IA debe decir **Claude** y el usuario debe ser **Marta Ruiz · Analista QA**.

## 1. Punto de partida (2 min) · consola de Azure DevOps

- **Boards**: cinco Features, cada una con los casos que el equipo ya automatizó a mano (#201 a #205).
- **Test Plans**: el plan de regresión agrupado por funcionalidad (Acceso, Catálogo, Carrito) y el plan «Release 2.4», donde se agrupa por versión.
- **La tienda** (pestaña 3): una web normal con un carrito, cupones y aviso de stock. Es la web contra la que se ejecutan los tests.

> «Hoy, pasar un documento funcional a tests automatizados y registrados en Azure es trabajo manual: leer el DFF, escribir cada test respetando los mapeos, ejecutarlo, abrir la PR y dar de alta cada Test Case en su Feature y su suite. Vamos a hacerlo con el asistente, y QA no va a perder el control en ningún momento.»

## 2. Subir el DFF (1 min)

- **Nueva ejecución** → botón `DFF_Carrito_cupones_v2.4.docx`.
- Destino: Feature **#103 Carrito y cupones**, plan **Release 2.4**, **suite nueva** «v2.4 · Carrito y cupones».
- **Crear ejecución y extraer casos**.

> «El DFF es un Word con una tabla de casos, tal como lo escribe el analista. No hace falta ninguna plantilla especial: luego veremos uno escrito en prosa.»

## 3. Gate 1: los casos (4 min)

Mientras extrae (unos 20 s), señala la **Actividad** de la derecha: documento leído, extracción con Claude y comparación con los casos que ya hay en Azure.

- **Seis casos extraídos.** TC-CARRITO-001 sale **descartado**: ya existe en Azure como #205. El asistente no duplica trabajo.
- **Avisos**: Claude lee el documento como lo haría un revisor exigente. Elige uno o dos:
  - TC-CARRITO-002: la precondición ya pone el producto en el carrito y el paso 1 lo vuelve a añadir. Con dos unidades el total esperado (80,10 €) no cuadraría.
  - «Se muestra el descuento» no dice qué importe comprobar.
  - TC-CARRITO-005 y 006 dependen de que haya exactamente 3 unidades en stock y el DFF no dice cómo garantizarlo.

  > «Estos avisos son preguntas que hoy aparecen a mitad de la automatización, o no aparecen. Aquí salen antes de escribir una línea de código.»
- **Edita un caso** (por ejemplo, completa el resultado esperado de TC-CARRITO-002 con «El descuento es de 8,90 €») y guarda. Lo que QA corrige es lo que se automatiza.
- Aprueba los cinco casos uno a uno. «Aprobar los que no tienen avisos» no sirve aquí, porque con Claude todos tienen alguno. Pulsa **Aprobar 5 casos y generar los tests**.
- Pestaña **Decisiones de QA**: cada aprobación queda con quién y cuándo.

## 4. Generación (2 min, se ve en directo)

Unos 80 segundos. Ve leyendo la actividad:

- **Contexto**: 40 componentes mapeados en 7 páginas y 2 page objects. El asistente parte del repositorio del equipo, no de cero.
- **Componente nuevo propuesto**: `carrito.cupon → [data-testid=carrito-cupon-input] (1 en el DOM)`. El cupón, el descuento y el aviso de stock no estaban en los mapeos. El asistente los busca en la página real y solo acepta un selector si existe en el DOM.
- **compila · reutiliza N componentes, M nuevos**: cada test se compila con `dotnet build` antes de aceptarlo.
- **Ejecutando 5 tests con Playwright (dotnet test)**: los cinco en verde.

> «El modelo no escribe donde quiere. Trabaja con herramientas acotadas: lee el repo, inspecciona la página y escribe el test. Si usa un selector suelto o un componente que no está mapeado, la herramienta se lo rechaza. Esas reglas están en nuestro código, no en el prompt.»

## 5. Gate 2: el código (3 min)

- **Mapeos nuevos que irán en la PR**: la tabla con los cinco componentes nuevos y sus selectores.
- Abre **TC-CARRITO-002** en el editor:
  - `new CarritoPage(Page).AnadirProductoAsync(productoId: 3)`: reutiliza el page object existente.
  - `Component(Page, "carrito.cupon").FillAsync("BIENVENIDA10")`: mapeos, nunca selectores sueltos.
  - Comprueba el total exacto, `80,10`.
  - `[Fact]`, `[Trait("Feature", "103")]`, `[Trait("Caso", "TC-CARRITO-002")]`, un método por caso con el ID en el nombre: las convenciones del equipo.
- Cambia una línea (por ejemplo, un comentario) y guarda: la pestaña **Cambios de QA** enseña el diff entre lo que generó la IA y lo que deja QA. Eso alimenta la métrica de «aceptados sin cambios».
- Opcional: **Sacar de la PR** un caso, para mostrar que QA puede dejar fuera lo que no le convenza.
- **Aprobar y abrir la pull request (5/5 en verde)**.

## 6. Pull request en Azure Repos (2 min)

- **Revisar la PR en Azure Repos** → la consola.
- La descripción lleva la tabla de casos con su resultado. El diff enseña un `.cs` por caso y solo las líneas nuevas de los mapeos.
- Intenta **Completar (merge)** sin aprobar: la política de rama lo impide.
- **Revisar como** `qa.lead` → **Aprobar** → **Completar (merge)**.
- Vuelve al asistente: en unos segundos detecta el merge solo.

> «La revisión de código es la de siempre. El asistente no se salta el proceso del equipo; entra por la puerta de la PR como cualquier otro cambio.»

## 7. Gate 3: registro en Azure (2 min)

- La vista previa enseña lo que se va a crear: cinco Test Cases en la Feature #103, con sus pasos, `AutomatedTestName = QaWeb.Tests.Generated.CarritoYCuponesTests.TC_CARRITO_002_AplicarUnCuponValido`, `AutomatedTestStorage = QaWeb.Tests.dll` y la suite «v2.4 · Carrito y cupones».
- **Confirmar el registro de 5 Test Cases**.
- En la consola, **Test Plans** → Release 2.4: la suite nueva con los cinco casos «Automatizado». Abre uno: pasos, enlace a la Feature y automatización asociada.

**Opcional, recuperación ante fallos** (hazlo antes de confirmar):

- En la consola, **Fallos** → **PAT caducado (401)**. Confirma el registro en el asistente: queda en error con el motivo, porque un 401 no se reintenta.
- **Quitar fallos** → **503 en 2 llamadas** → **Reintentar** en el asistente. En la actividad aparecen los reintentos («Azure DevOps devuelve 503; reintento 1…») y el registro termina. Ningún Test Case sale duplicado: cada caso guarda su id de Azure en cuanto se crea.
- **Quitar fallos** al terminar.

## 8. Medición (2 min)

- **Dashboard**: tests registrados, en verde a la primera, aceptados sin cambios, coste de IA por test (unos 8 céntimos) y el tiempo de cada fase del asistente frente al de QA. La línea base (minutos por caso hoy) la pone el equipo; el resto se mide.

> «Esto es lo que se mediría con DFF reales: tiempo por caso, cuánto se acepta sin tocar y cuánto cuesta.»

## 9. Cierre (1 min)

- Otro formato de DFF: abre la ejecución del checkout preparada. El documento está en prosa; los tres tests salieron en verde a la primera y reutilizan siete componentes mapeados sin proponer ninguno nuevo.
- Qué cambia para llevarlo a un entorno real: el formato de mapeos del equipo (aislado en un adaptador), la URL y el PAT de Azure DevOps y los proyectos de test. Appium para móvil es el siguiente paso: cambian el ejecutor y el inspector, y el flujo y el registro son los mismos.

## Variante: un DFF en borrador (si hay tiempo o preguntan «¿y si el DFF está mal?»)

`DFF_Area_cliente_borrador.docx` (Feature #105) tiene pasos vagos, un resultado esperado ausente y una contraseña contradictoria.

- **Gate 1**: los tres casos salen con avisos. Por ejemplo: «Realizar un pedido» no dice qué producto ni cómo pagar, a TC-PERFIL-003 le falta el resultado esperado, y la contraseña del paso (`Demo1234`) no coincide con la de los datos de prueba (`Bloq2024`).
- Si se aprueban igualmente, **la IA no se inventa lo que falta**. TC-PERFIL-001 sale en verde. En los otros dos deja el test escrito hasta donde puede y lo cierra con `NotImplementedException` y el motivo, por ejemplo: «falta el resultado esperado en el caso, y hay que aclarar qué contraseña usar (Demo1234 o Bloq2024)». En el Gate 2 aparecen en rojo con ese mensaje; se sacan de la PR y vuelven al analista.
- Tarda más (unos 3 minutos), porque los tests en rojo pasan por la autocorrección. Para la demo basta con enseñar el Gate 1 y **Descartar ejecución**.

> «Prefiere dejar un hueco señalado a rellenarlo con una suposición. Un test que pasa comprobando lo que no es resulta peor que no tenerlo.»

## Si algo falla en directo

| Problema | Qué hacer |
|---|---|
| La API de Claude tarda o falla | La ejecución queda en error con el motivo. **Reintentar** retoma la fase. Si persiste, enseña la ejecución del checkout preparada, que tiene el recorrido entero. |
| Sin red | `QA_AI=mock` en `.env` y reinicia (`pkill -f honcho`, `make up`). El flujo es el mismo con la IA simulada; avisa de que el código lo genera un traductor de reglas. |
| Un test sale en rojo | Bien para la demo: con Claude vuelve al modelo con el error real (pestaña **Autocorrección**). Si sigue en rojo, **Sacar de la PR**. |
| La PR no avanza | **Comprobar ahora** en el asistente. Recuerda que hace falta el voto de `qa.lead` antes de completar. |

## Preguntas que suelen salir

- **¿Cuánto cuesta?** Unos 7-8 céntimos de dólar por test con el modelo más capaz, gracias a la caché del contexto del repositorio. Un DFF de 20 casos, menos de 2 $.
- **¿A dónde van los documentos?** A la API del modelo, solo lo necesario: el DFF, los mapeos y los page objects. Se puede usar sin retención de datos o a través de un proveedor de nube; el modelo va detrás de un adaptador y se puede cambiar.
- **¿Y si genera un test malo?** No llega a `main` sin pasar por QA (Gate 2) y por la PR del equipo. Además, no se acepta si no compila, si usa selectores sueltos o si propone un componente que no está en la página.
- **¿Usa nuestros mapeos?** Sí, y propone los que faltan en el mismo formato, una entrada por línea, para que el diff de la PR sea legible.
- **¿Qué hace QA entonces?** Lo que aporta valor: revisar los casos, decidir qué se automatiza, revisar el código y aprobar. Escribir el código repetitivo y dar de alta en Azure lo hace el asistente.
