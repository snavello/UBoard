# UBoard — Fase 3: lectura, dudas, decisiones técnicas, plan y skills

Fecha: 2026-09-10. Estado: para aprobación de Sd antes de escribir código.
Fuente: `docs/especificacion-v1.md` §1 (principio 4), §4, §6 ("Constructor:
carga y modelado" paso 7, "Visualizador" punto 3), §7, §8, §9, §10.

## (1) Lectura de la fase 3

Objetivo: **un solo asistente, dos usos.** El mismo motor de conversación
con Claude, con distinto juego de herramientas según quién pregunta: el
constructor puede pedirle que modifique el modelo o el dashboard ("agregá
un gráfico de ventas por sucursal por mes"); el visualizador solo puede
preguntar sobre los datos ("¿cuánto vendió Pérez en marzo?"), respetando los
filtros activos. Claude nunca escribe SQL: en el chat, cada pedido se
traduce a una **operación** (las del wizard, más las nuevas del dashboard) o
a una **consulta semántica** (la misma que ya arma el compilador desde el
paso 5); el motor de consultas no cambia.

Principio rector (§1.4): **un solo motor, dos interfaces.** El wizard aplica
`POST /modelo/operaciones` con un cuerpo `{"operacion": "...", ...}`
armado por un formulario; el chat va a aplicar exactamente la misma
operación, armada por Claude a partir de una frase. El historial y el
deshacer no son una funcionalidad nueva: ya existen porque cada operación
crea una versión con diff (paso 12); falta hacer lo mismo para el
dashboard y exponerlo en la UI.

Entra en la fase 3 (§6, §9):
1. **Operaciones granulares del dashboard**, el mismo mecanismo del §4 pero
   para `SpecDashboard`: crear/editar/eliminar filtro, KPI, gráfico y
   pestaña del explorador. El wizard de hoy no las necesita (el spec sale
   entero del generador), pero el chat sí: es la única forma de que
   Claude pueda "agregar un gráfico" sin tocar el JSON.
2. **Historial y deshacer**, ya para modelo y dashboard: una pantalla que
   lista las versiones con su resumen y diff, y un botón para volver a
   cualquiera (deshacer = volver a la anterior).
3. **Expresiones aritméticas libres entre métricas** (Sd las pidió para
   esta fase): `margen = ventas - costos`, no solo cociente.
4. **Chat constructor**: una conversación con tools de escritura sobre
   modelo y dashboard (§8: "tools de escritura", exactamente las
   operaciones granulares) más la de lectura. Cada acción que toma queda
   en el historial como si la hubiera hecho el wizard.
5. **Preguntas en lenguaje natural** del visualizador (y también
   disponible para el constructor, de solo lectura): Claude recibe el
   modelo semántico y los filtros activos, devuelve una consulta
   semántica, se compila y ejecuta, y Claude redacta la respuesta en
   texto a partir del resultado (nunca inventa el número).

No entra (fase 4): filtrado asociativo, texto estructurado, calidad de
datos, resubida con diff de esquema, S3/R2, Render.

Aceptación (§9): *"agregá un gráfico de ventas por sucursal por mes"
produce el gráfico correcto; "¿cuánto vendió Pérez en marzo?" responde bien
respetando los filtros activos.*

## (2) Dudas y ambigüedades (cada una con propuesta)

Alcance del chat
1. **Un chat o dos.** ¿El constructor tiene una sola conversación con
   acceso a las tools de modelo y de dashboard juntas, o son dos chats
   separados (uno por pantalla)? Propuesta: **uno solo**, disponible desde
   cualquier pantalla del constructor (barra lateral o panel que se abre y
   cierra), porque para la persona es "hablarle a UBoard", no elegir a qué
   parte del sistema le habla.
2. **Dónde vive la pregunta del visualizador.** Propuesta: un cuadro de
   pregunta en el Tablero mismo, cerca de los filtros (tiene que respetar
   los que estén activos). El constructor lo tiene ahí también, además del
   chat de escritura.
3. **Se guarda la conversación.** ¿El historial de mensajes del chat queda
   en la base (tabla nueva, para retomarlo después de cerrar el
   navegador) o alcanza con que viva en el estado de la pantalla y se
   pierda al refrescar? Propuesta: **no persistir la conversación** en
   esta fase. Lo que importa queda igual: cada acción real sobre el
   modelo o el dashboard es una versión con diff, eso sí persiste. Si más
   adelante hace falta retomar una charla, se agrega una tabla `mensaje`
   sin tocar el resto.
4. **Progreso mientras responde.** Un pedido de chat puede tardar varios
   segundos (Claude decide qué herramienta usar, la ejecutamos, le
   devolvemos el resultado, redacta la respuesta final: dos llamadas como
   mínimo). Propuesta: **sin streaming por ahora**, un pedido que devuelve
   la respuesta completa con un indicador de "pensando..." en la UI. SSE
   (mencionado como pendiente desde la fase 1) queda para más adelante si
   se nota lento; no es necesario para la aceptación.

Historial y deshacer
5. **Alcanza con "restaurar cualquier versión".** Propuesta: un único
   mecanismo, `restaurar(numero)`, que crea una versión nueva con el
   contenido de esa versión vieja (nunca se reescribe el historial).
   "Deshacer" es restaurar la versión anterior a la actual; si te
   arrepentís de haber deshecho, restaurás la que tenías. No hace falta un
   botón "rehacer" aparte.
6. **Quién puede deshacer.** Propuesta: mismo rol que edita (constructor).
   El visualizador ni ve el historial.

Expresiones aritméticas
7. **Qué operaciones hacen falta.** Propuesta: suma, resta, multiplicación
   y división entre métricas de agregación (o entre otras fórmulas,
   anidando) y constantes numéricas — un árbol, no una fórmula en texto
   libre, para poder validarla siempre y que Claude nunca escriba algo que
   no sepamos traducir a SQL con seguridad. ¿Alcanza con estos cuatro
   operadores?
8. **Quién las crea.** Ya están las dos vías: a mano en el wizard
   (formulario con selects, como hoy con el cociente) y por chat
   ("creá una métrica margen que sea ventas menos costos").

Costo y modelo de Claude
9. **Tope de gasto.** El chat se usa más seguido que la inferencia (que es
   una vez por dataset). ¿Seguimos con el mismo tope de USD 10 para toda
   la fase, avisando si se acerca, o preferís uno nuevo para esta fase?
10. **Qué modelo.** Propuesta: `claude-sonnet-5` por defecto, igual que
    hoy (el tool-use con muchas herramientas anda mejor con un modelo más
    grande); queda configurable a Haiku 4.5 si en algún momento el costo
    importa más que la velocidad de respuesta.

Datos
11. Recordatorio, no bloqueante: seguimos con los 5 CSV sintéticos. Si ya
    tenés los reales, es un buen momento para probarlos.

## (3) Decisiones técnicas propuestas

Chat con Claude (tool use real, no salida estructurada de un solo pedido)
- `ClienteLLM` (paso 11) gana un método nuevo para conversación con
  herramientas (`conversar`), separado de `completar` (que sigue para la
  inferencia): manda `messages.create(tools=[...], messages=[...])`,
  si la respuesta trae `tool_use` lo ejecutamos y le devolvemos el
  resultado como `tool_result`, hasta que responda con texto. Tope de 4
  vueltas por mensaje (evita loops raros); si se pasa, error claro.
- **Una herramienta de Claude por operación**, no una sola con un campo
  "operacion" adentro: Claude elige mejor por nombre de herramienta que
  por un valor dentro de un esquema grande. El `input_schema` de cada
  herramienta sale de `model_json_schema()` de la clase Pydantic que ya
  existe en `modelo/edicion.py` (paso 12) y en el nuevo
  `dashboard/edicion.py`: cero esquemas duplicados. Total aproximado: 21
  del modelo + 8 del dashboard + 1 de lectura + 1 de deshacer ≈ 30.
- `app/asistente/herramientas.py`: arma la lista de herramientas según el
  rol (visualizador = solo la de lectura) y el diccionario
  nombre → función que la aplica (reusa `aplicar_operacion` /
  `aplicar_operacion_spec` + `guardar_version`, y `consultar(...)` del
  motor para la de lectura).
- `app/asistente/motor.py`: prompt de sistema (rioplatense, "no
  inventes un número: siempre lo sacás de la herramienta de consulta"),
  arma el pedido con el modelo efectivo + resumen de la fuente + filtros
  activos, corre el loop, devuelve texto + qué operaciones aplicó (para
  mostrar "hecho: se creó el gráfico X" en el chat) + la consulta y su
  resultado si usó la de lectura (para ofrecer un gráfico, no solo texto).
- Sin caché de respuestas (a diferencia de la inferencia): cada pregunta
  es distinta, no tiene sentido cachear por huella. Si el costo preocupa,
  se puede sumar más adelante un caché de la ÚLTIMA consulta compilada por
  pregunta textual idéntica.

Dashboard: operaciones granulares (`app/dashboard/edicion.py`)
- Mismo patrón que `modelo/edicion.py`: `Operacion` discriminada por
  `operacion`, `aplicar_operacion(spec, operacion) -> (spec, resumen)`
  pura, `POST /dashboard/operaciones` valida con `validar_spec` (compila
  cada panel, como ya hace `PUT /dashboard`) y usa el `guardar_version`
  que ya existe.
- Operaciones: `crear_filtro`, `editar_filtro`, `eliminar_filtro`,
  `crear_kpi`, `eliminar_kpi`, `crear_grafico`, `editar_grafico`,
  `eliminar_grafico`, `crear_pestania`, `editar_pestania`,
  `eliminar_pestania`, `reordenar_kpis` (para cambiar el protagonista sin
  recrear todo). Nuevos códigos `E-SPEC-07` (operación desconocida) y
  `E-SPEC-08` (no aplicable).

Deshacer
- `operaciones.restaurar(sesion, workspace, numero) -> VersionModelo`
  (y su espejo para spec): valida que la versión exista, la vuelve a
  guardar con `guardar_version(..., operacion="restaurar", resumen=f"Se
  restauró la versión {numero}")`. `POST /modelo/versiones/{numero}/restaurar`
  y `POST /dashboard/versiones/{numero}/restaurar`.

Expresiones aritméticas (`ExpresionFormula`)
- En `modelo/esquema.py`: `ExpresionFormula { operacion: suma|resta|
  multiplicacion|division, izquierda: Operando, derecha: Operando }`,
  `Operando = IdCorto | float | ExpresionFormula` (árbol recursivo,
  Pydantic v2 soporta el forward ref). `Metrica.expresion` pasa a
  `ExpresionAgregacion | ExpresionCociente | ExpresionFormula`.
- `consultas/compilador.py`: generaliza lo que hoy hace solo con
  `ExpresionCociente` (recolectar las métricas referenciadas para
  agregarlas, y armar la expresión SQL después de agregar) a cualquier
  árbol de `ExpresionFormula`; división anidada lleva su propio
  `NULLIF(..., 0)`. `modelo/validacion.py`: ciclos entre fórmulas se
  detectan con el mismo mecanismo que ya evita que un cociente se
  referencie a sí mismo.
- Wizard: en "Crear métrica" un tercer tipo además de agregación y
  cociente, con selects anidables (alcance simple: dos operandos con un
  operador, como el cociente hoy; anidar de a uno "envolviendo" el
  resultado en otra fórmula, no un editor de árbol completo).

Frontend
- `asistente/Chat.tsx`: lista de mensajes, input, indicador de "pensando",
  y por cada acción aplicada una línea tipo "✓ Se creó el gráfico
  'Ventas por sucursal'" con link a Modelo o al gráfico. Mismo componente
  para el chat de escritura (constructor) y el cuadro de preguntas
  (visualizador), con una prop que dice qué endpoint/tools tiene
  disponibles el backend (el frontend no elige tools, eso lo decide la
  API según el rol de la sesión).
- Historial: pestaña o sección nueva en Modelo (y una futura en
  Dashboard) con la lista de versiones ya existente, ahora con diff
  legible y botón "Restaurar esta versión".

## (4) Plan por pasos (cada uno: tests en verde, CLAUDE.md, commit, resumen)

- **Paso 16 — Operaciones del dashboard.** `dashboard/edicion.py` + `POST
  /dashboard/operaciones`. Sin Claude todavía.
- **Paso 17 — Historial y deshacer.** `restaurar` para modelo y spec +
  UI de historial con diff legible.
- **Paso 18 — Expresiones aritméticas.** Esquema, compilador,
  validación de ciclos, operación `crear_metrica` con fórmula, wizard.
- **Paso 19 — Motor del asistente.** `ClienteLLM.conversar`, catálogo de
  herramientas por rol, prompt, loop, endpoint único de chat. Cliente
  falso para tests (nunca red), como en la fase 2.
- **Paso 20 — Chat del constructor.** UI, verificar "agregá un gráfico de
  ventas por sucursal por mes" de punta a punta.
- **Paso 21 — Preguntas del visualizador.** Cuadro de pregunta en el
  Tablero, disponible también para el constructor; verificar "¿cuánto
  vendió Pérez en marzo?" respetando filtros activos.
- **Paso 22 — Integración y aceptación de la fase 3.**
  `docs/fase3-aceptacion.md` con los dos casos de la spec y el resto del
  checklist, en Docker.

## (5) Skills y herramientas a usar

- Agente `claude-code-guide` antes del paso 19, para confirmar la forma
  vigente de tool use multi-turno con el SDK (`messages.create` con
  `tools`, formato de `tool_result`) igual que se hizo con la salida
  estructurada en la fase 2.
- `frontend-design` del repo para el chat (misma dirección editorial).
- Resto igual: pytest por archivo, vitest, Docker Compose.

## (6) Qué se necesita de Sd

- Respuestas a las dudas 1 a 11 (de a una).
- Si tiene los 5 CSV reales, es un buen momento para probarlos contra el
  chat.

## (7) Respuestas de Sd (2026-09-10)

Aprobado el plan. Respuestas a las dudas:
1. Un solo chat con las tools de modelo y dashboard juntas.
2. Cuadro de pregunta en el Tablero, también disponible para el constructor.
3. No persistir la conversación en esta fase.
4. Sin streaming por ahora; SSE queda para más adelante si hace falta.
5. Un único mecanismo "restaurar versión"; deshacer = restaurar la anterior.
6. Deshacer solo para el constructor.
7. Suma, resta, multiplicación y división alcanzan.
8. (informativa, sin pregunta).
9. Mismo tope de USD 10 para toda la fase.
10. `claude-sonnet-5` por defecto, configurable a Haiku 4.5.
11. (recordatorio, sin respuesta pendiente).
