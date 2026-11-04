# Guion de la demo (unos 15 minutos)

Preparación: `make seed && make up`. Abre tres pestañas: el asistente (http://localhost:8600), la consola de Azure DevOps simulada (http://localhost:8601/console) y la web (http://localhost:8602).

## 1. Punto de partida (2 min)

- **Azure DevOps · Boards**: cinco Features y cinco casos ya automatizados por el equipo.
- **Test Plans**: el plan de regresión agrupado por funcionalidad y el plan «Release 2.4», que todavía está vacío.
- Mensaje: «Hoy, pasar un DFF a tests registrados es trabajo manual. Vamos a hacerlo con el asistente, sin que QA pierda el control».

## 2. Subir el DFF (1 min)

- **Nueva ejecución** → `DFF_Carrito_cupones_v2.4.docx`, Feature #103, plan «Release 2.4», suite nueva «v2.4».

## 3. Gate 1: casos (3 min)

- Seis casos extraídos de la tabla. **TC-CARRITO-001 ya existe en Azure** (#205): el asistente lo detecta y lo deja descartado.
- Edita un caso para enseñar que QA corrige antes de generar, y aprueba el resto.
- Variante: el DFF `DFF_Area_cliente_borrador.docx` enseña los avisos (paso vago, resultado esperado ausente, contraseña contradictoria).

## 4. Generación y Gate 2: código (4 min)

- En la actividad se ve cómo reutiliza los page objects (`CarritoPage`, `LoginPage`) y los componentes mapeados.
- **Mapeos nuevos**: el cupón, el descuento y el aviso de stock no estaban mapeados. Los ha buscado en el DOM real y los propone con su selector.
- Todos los tests en verde contra la web (`dotnet test`, xUnit). Abre uno en el editor y enseña el diff.
- Aprueba: se publica la rama y se abre la PR.

## 5. Pull request en Azure Repos (2 min)

- En la consola: la descripción con la tabla de casos y el diff de los `.cs` y de los mapeos (solo líneas nuevas).
- Como `qa.lead`: **Aprobar** → **Completar (merge)**. Sin aprobación, la política de rama no deja completar.

## 6. Gate 3: registro (2 min)

- El asistente detecta el merge y enseña qué va a crear: Test Cases dentro de la Feature #103, con los pasos, `AutomatedTestName` y suite «v2.4».
- Confirma. En **Test Plans** aparece la suite con los cinco casos marcados como «Automatizado» y la etiqueta del asistente.

## 7. Recuperación y medición (1 min)

- **Fallos** → «503 en 2 llamadas» y repite un registro: los reintentos aparecen en la actividad y no se duplica nada.
- **Dashboard**: tiempos del asistente frente a los de QA, verde a la primera, aceptados sin cambios, reutilización de mapeos y coste de IA por test (con Claude).

## Con IA real

Con `QA_AI=claude` se repite el recorrido. Con el DFF en prosa (`DFF_Checkout_v2.4.docx`) se ve que no depende de un formato fijo, y la autocorrección actúa si algún test falla.
