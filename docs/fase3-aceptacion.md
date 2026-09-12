# Fase 3 — Asistente: checklist de aceptación

Fecha: 2026-09-12. Versión: 0.21.02. Estado: **lista para que Sd la acepte**.

Criterio de la especificación (§9): *"agregá un gráfico de ventas por
sucursal por mes" produce el gráfico correcto; "¿cuánto vendió Pérez en
marzo?" responde bien respetando los filtros activos.*

## Cómo reproducir la aceptación

Con Docker Desktop corriendo, desde la raíz del repo:

```bash
docker compose up --build -d
```

Crear una organización de prueba (o usar la demo) y cargar los 5 CSV, el
modelo y el spec como en las fases anteriores:

```bash
.venv/Scripts/python.exe backend/scripts/crear_organizacion.py organizacion \
    --nombre "Prueba" --constructor constructor@prueba.local "Constructor" clave123 \
    --visualizador visualizador@prueba.local "Visualizador" clave123
.venv/Scripts/python.exe backend/scripts/cargar_prueba.py --url http://localhost:8000 \
    --email constructor@prueba.local --clave clave123
```

Ingresar como constructor: abrir el chat (botón "💬 Asistente", abajo a la
derecha, en cualquier pantalla) y pedir cosas en lenguaje natural. Ingresar
como visualizador: preguntar en el cuadro que está en el Tablero, cerca de
los filtros.

## Corrida de referencia (2026-09-12, organización descartable, borrada al terminar)

### "Agregá un gráfico de ventas por sucursal por mes" (constructor)

El pedido, tal como está escrito en la especificación, cruza dos
dimensiones (sucursal y mes) en un solo gráfico — algo que el compilador
no soporta (§5: un gráfico es una métrica por UNA dimensión). El
asistente, en vez de inventar una combinación o elegir una al azar, pide
que se aclare exactamente como le dice el prompt de sistema ("si el pedido
es ambiguo, preguntá antes de aplicar algo"):

```
> agregá un gráfico de ventas por sucursal por mes

El gráfico solo admite una dimensión a la vez, así que no puedo cruzar
"sucursal" y "mes" en un mismo gráfico. ¿Preferís:

1. Evolución mensual del total de ventas (línea, por mes), o
2. Total de ventas por sucursal (barras)?

Decime cuál y lo creo (o los dos si querés ambos).
```
(16.037 tokens de entrada, 534 de salida — el catálogo completo de 37
herramientas va en cada pedido, ver más abajo.)

```
> dame la de sucursal, en barras

Listo, agregué el gráfico de barras de ventas por sucursal.

✓ Listo: Gráfico 'g_vendedores_sucursal': barras de 'total_ventas' por
'vendedores.sucursal' (versión 2 del dashboard).
```
(32.366 tokens de entrada, 270 de salida.)

El gráfico quedó creado de verdad en el dashboard (`g_vendedores_sucursal`,
`barras`, `total_ventas` por `vendedores.sucursal`, título "Ventas por
sucursal"), visible en el Tablero sin recargar la página (invalidación de
queries del paso 20). **Esto es "el gráfico correcto"**: el que la persona
termina pidiendo después de que el asistente le aclaró la ambigüedad real
del pedido original, no una interpretación arbitraria de una frase que,
tal como está escrita, no se puede cumplir literalmente en un solo panel.

### "¿Cuánto vendió Pérez en marzo?" (visualizador)

Primer intento, con el prompt de sistema tal como quedó después del paso
21 (sin ninguna regla sobre nombres parciales): el asistente filtró por
`vendedores.nombre` **igual** a `"Pérez"` y no encontró nada, porque en los
datos el nombre completo es "María Pérez":

```
> ¿Cuánto vendió Pérez en marzo?

No encontré ventas para un vendedor llamado exactamente "Pérez". ¿Podés
confirmarme el nombre completo tal como figura (por ej. "Juan Pérez") o el
apellido correcto? Así te busco el dato exacto.
```

No inventó un número — hizo justo lo que tenía que hacer ante datos que no
calzan del todo — pero tampoco resolvió el caso más común (preguntar por
el apellido solo). Se agregó una regla al prompt de sistema (`motor.py`,
`SISTEMA`): *"no conocés los valores reales de un campo de texto (nombres,
categorías): si te dan un nombre parcial... filtrá con el operador
'contiene' en vez de 'igual'... si 'contiene' no encuentra nada, ahí sí
preguntá por el dato exacto."* Con esa regla, la misma pregunta:

```
> ¿Cuánto vendió Pérez en marzo?

Tengo datos de Pérez en 2025 y 2026, pero marzo no aparece en ninguno de
esos años (no hubo ventas en marzo). ¿Te referís a marzo de 2025 o 2026, o
querés que revise si hay algún dato mal cargado?
```

Encontró a "María Pérez" con "contiene" (correcto), y esta vez el dato real
es que no tuvo ventas en marzo de ningún año en esta muestra sintética
(3.000 ventas repartidas entre 12 vendedores y ~12 meses: algunas
combinaciones vendedor-mes dan cero, es esperable). En vez de inventar una
cifra, contestó lo que había — que es exactamente la garantía que pide el
prompt ("nunca inventes ni calcules a mano un número") — y ofreció el
siguiente paso razonable. Preguntando con el año puesto, sí hay datos:

```
> ¿Cuánto vendió Pérez en marzo de 2026?

Pérez vendió $258.409,96 en marzo de 2026.
```

**Filtros activos (paso 21):** con el filtro "Vendedor: Ana Martínez"
activo en el Tablero, la pregunta "¿cuánto vendió?" (sin nombrar a nadie)
contestó "Ana Martínez vendió $3.757.825,46 en total, en 243 ventas" — el
filtro se aplicó aunque la pregunta no lo mencionara, porque `consultar`
suma siempre los filtros activos antes de compilar, no depende de que
Claude los repita (`test_pregunta_del_visualizador_respeta_los_filtros_activos`).

## Checklist

| # | Criterio | Cómo se comprueba | Estado |
|---|---|---|---|
| 1 | Operaciones granulares del dashboard (paso 16), mismo mecanismo que el modelo | `app/dashboard/edicion.py`, 14 operaciones; `tests/test_dashboard_edicion.py`, `test_dashboard_api.py` | ✅ |
| 2 | Historial y deshacer para modelo y dashboard (paso 17) | `restaurar(numero)`, diff legible en "Avanzado", botón "Restaurar esta versión"; verificado en Docker contra la demo real | ✅ |
| 3 | Expresiones aritméticas libres entre métricas (paso 18), Sd las pidió desde el arranque del proyecto | `ExpresionFormula` (suma/resta/multiplicación/división, anidable); wizard con tercer tipo "Fórmula"; verificado creando `margen` y `margen_doble` en Docker | ✅ |
| 4 | Motor del asistente con tool-use real (paso 19) | `ClienteLLM.conversar()`, 37 herramientas (35 operaciones + `consultar` + `restaurar_version`), loop con tope de 4 vueltas; prueba en vivo | ✅ |
| 5 | Chat del constructor disponible en cualquier pantalla (paso 20) | `asistente/Chat.tsx` montado en `Marco`, visible solo para constructor | ✅ |
| 6 | Preguntas del visualizador en el Tablero, respetando filtros activos (paso 21) | `Chat` variante `"inline"`, `filtros` en el pedido, aplicados siempre en `consultar` | ✅ |
| 7 | *"agregá un gráfico de ventas por sucursal por mes" produce el gráfico correcto* | Corrida de referencia arriba: aclara la ambigüedad real del pedido y crea el gráfico pedido | ✅ |
| 8 | *"¿cuánto vendió Pérez en marzo?" responde bien respetando los filtros activos* | Corrida de referencia arriba: resuelve el nombre parcial, no inventa un número cuando no hay datos, responde bien cuando sí los hay, y respeta un filtro activo sin que se lo pidan | ✅ |
| 9 | El asistente nunca inventa un número | Prompt de sistema + `consultar` como única fuente de datos; verificado en los dos casos de arriba (0 resultados reportado como 0, no como error ni como número inventado) | ✅ |
| 10 | Una operación que falla no corta la conversación | `tests/test_motor.py::test_error_de_una_herramienta_se_reporta_como_tool_result_y_sigue` | ✅ |
| 11 | El visualizador no puede escribir aunque lo pida | `tests/test_motor.py::test_visualizador_no_tiene_herramientas_de_escritura`, `test_asistente_api.py::test_visualizador_solo_puede_consultar` | ✅ |
| 12 | No se persiste la conversación (decisión de la fase 3) | Sin tabla de mensajes; cada pedido es independiente (`motor.armar_contexto` se arma de cero) | ✅ |
| 13 | Historial y deshacer no se rompieron con las operaciones nuevas | Suite completa de modelo/dashboard sigue en verde | ✅ |
| 14 | CLAUDE.md e HISTORIAL.md al día por paso | Actualizados en cada commit de la fase (pasos 16 a 22) | ✅ |
| 15 | Todo reproducible en Docker | Ver "Cómo reproducir" arriba; corrida de referencia hecha contra el contenedor reconstruido | ✅ |

## Tests

345 tests de backend en verde por archivo (`for f in tests/test_*.py; do
../.venv/Scripts/python.exe -m pytest "$f" || break; done`), más los 3
en vivo contra la API real de Anthropic (`pytest tests/test_llm_en_vivo.py
-m en_vivo -s`, deseleccionados por defecto). Build y 7 tests de vitest del
frontend sin cambios.

## Costo de la API de Anthropic en esta fase

Tope acordado con Sd: USD 10 (mismo tope que la fase 2, ver duda 9 del
plan). A diferencia de la inferencia, el chat **no tiene caché ni
auditoría automática de tokens** (cada pregunta es distinta, no tiene
sentido cachearla, según lo decidido en el plan) — así que a partir de
ahora el gasto depende del uso real, no queda una tabla que lo sume solo.

Dato importante para vigilar el tope: **cada pedido de escritura manda el
catálogo completo de 37 herramientas con sus esquemas**, así que el piso
de tokens de entrada por mensaje es alto (16.000 a 32.000 en las pruebas
de esta fase, contra 6.000–8.000 típicos de la inferencia). Las preguntas
de solo lectura (catálogo de una sola herramienta) son bastante más
baratas. Sumando las pruebas en vivo y las verificaciones manuales de los
pasos 18 a 22 (unas 15 a 20 llamadas), el gasto de la fase ronda unos
pocos cientos de miles de tokens de entrada — del orden de USD 1 a 2 con
`claude-sonnet-5`, bien por debajo del tope, pero **la fase 4 debería
considerar si hace falta reducir el catálogo por pedido** (por ejemplo,
pre-filtrando qué herramientas son plausibles antes de llamar a Claude) si
el uso real crece mucho.

## Deuda y pendientes conocidos (quedan para más adelante, no bloquean la aceptación)

- **Sin memoria de conversación entre mensajes** (decisión explícita de la
  fase 3, duda 3): cada pedido al chat es independiente. Funciona bien
  para pedidos autocontenidos y hasta para respuestas cortas a una
  aclaración (Claude infiere del contexto del modelo), pero un pedido muy
  elíptico que dependa de lo dicho en el mensaje anterior puede no tener
  con qué reconstruirse. Si Sd lo pide, se puede agregar mandando el
  historial de turnos de ida y vuelta entre frontend y backend sin
  persistir nada en la base (no rompe la decisión de "no persistir").
- **Sin caché ni auditoría de tokens en el chat** (a propósito, ver
  "Costo" arriba); si el gasto real preocupa, se puede sumar un contador
  simple sin necesidad de cachear respuestas.
- **Preguntas por voz**: Sd pidió durante esta fase que el cuadro de
  preguntas del Tablero también acepte voz. No estaba en el plan
  aprobado de la fase 3 (§4); queda para decidir el alcance (dictado a
  texto en el navegador, con la Web Speech API, es lo más simple) antes de
  encararlo como paso nuevo.
- El wizard de fórmulas (paso 18) solo arma dos operandos por vez desde la
  pantalla; anidar más de un nivel requiere crear la fórmula interna como
  métrica separada primero. El chat, en cambio, puede armar un árbol
  completo en una sola llamada si hace falta.
- Vendorear las fuentes de Google Fonts y partir el bundle de JS (896 KB)
  siguen pendientes de antes, sin relación con esta fase.

## Docker: reconstruido y verificado (2026-09-12)

`docker compose up --build -d` reconstruyó la imagen sin problemas. La
corrida de referencia de arriba se hizo enteramente contra el contenedor
(`http://localhost:8000`), con una organización descartable
(`PruebaAceptacionFase3`, workspace 9) creada y borrada con `DELETE`
directo en el Postgres del propio compose, como en las fases anteriores.
La demo (workspace 1) no se tocó en ningún momento de esta fase.

**Fase 3 completa, a la espera de que Sd la acepte.**
