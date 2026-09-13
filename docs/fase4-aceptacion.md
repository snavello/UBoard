# Fase 4 — Interacción y filtrado asociativo: checklist de aceptación

Fecha: 2026-09-13. Versión: 0.26.01. Estado: **lista para que Sd la acepte**.

A diferencia de las fases 1 a 3, esta fase arrancó de forma ad-hoc, a
pedido directo de Sd en medio de la sesión de aceptación de la fase 3
("actuá como Qlik... la funcionalidad del panel sindical de Mi Trabajo"),
sin el documento de lectura/dudas/decisiones/plan completo que llevan las
fases anteriores. No tiene entonces un único criterio de aceptación
escrito de antemano como el §9 que usaron las fases 1 a 3; el criterio
real es el pedido de Sd, más lo que la especificación rectora ya decía
sobre el "dashboard asociativo" desde el principio:

> [`docs/especificacion-v1.md`](especificacion-v1.md) §1: *"...propone un
> **dashboard asociativo**..."* — §6 (Visualizador, paso 1): *"Aplica
> filtros → `asociativo` calcula, por entidad, valores compatibles
> (verde) e incompatibles (gris) propagando por el grafo de relaciones."*

Esta fase entrega una PRIMERA porción de eso — filtrado por click y por
chat, más el gris en las opciones de un filtro — no la versión completa
del párrafo citado (que además propone un módulo `asociativo/` propio con
cache por combinación de filtros, cosa que no hizo falta: se resolvió con
lo que ya existía). El resto (gráficos también en gris, propagación
completa por el grafo) queda deliberadamente aplazado — ver "Pendientes".

## Qué entrega esta fase

1. **Paso A — click-to-filter y el asistente aplica un filtro existente**
   (v0.23.01): clickear una barra o porción de un gráfico alterna ese
   valor como filtro del dashboard; pedirle al chat "aplicá el filtro
   de X" hace lo mismo por lenguaje natural. Mismo mecanismo para las dos
   cosas (`FiltrosActivos`, ya existía desde la fase 1).
2. **Diagrama del modelo tipo DER** (v0.24.01): pestaña nueva en Modelo
   con el modelo semántico dibujado como entidad-relación, notación
   "pata de gallo" real. No es filtrado asociativo, pero salió del mismo
   pedido ("evaluá la posibilidad de ver el modelo gráfico... tipo DER").
3. **Métricas con un filtro propio** (v0.25.01): una métrica puede llevar
   una condición pegada (ej. "ventas en efectivo"), utilizable desde el
   wizard y desde el chat, incluyendo el ejemplo textual exacto de Sd
   ("torta ventas en efectivo por vendedor").
4. **Estado gris, versión chica: opciones de filtro** (v0.26.01): las
   opciones de un filtro de lista se pintan distinto (grisadas, sin
   sacarlas de la lista) cuando los OTROS filtros activos ya no
   producirían resultado con esa opción.

## Cómo reproducir

```bash
docker compose up --build -d
```

```bash
.venv/Scripts/python.exe backend/scripts/crear_organizacion.py organizacion \
    --nombre "Prueba" --constructor constructor@prueba.local "Constructor" clave123 \
    --visualizador visualizador@prueba.local "Visualizador" clave123
.venv/Scripts/python.exe backend/scripts/cargar_prueba.py --url http://localhost:8000 \
    --email constructor@prueba.local --clave clave123
```

## Corrida de referencia (2026-09-13, organización descartable `PruebaAceptacionFase4`, workspace borrado al terminar)

Se hizo una corrida combinada, tocando las cuatro piezas en la misma
sesión de navegador, contra el contenedor reconstruido — no cada pieza
aislada como en las verificaciones de cada paso, para confirmar que
siguen andando juntas.

**Diagrama** (Modelo → pestaña "Diagrama"): las 5 entidades del dataset
de prueba (`ventas`, `vendedores`, `productos`, `pagos`, `medios_pago`)
aparecen como cajas con notación pata de gallo real, cabecera violeta
para `ventas` (hechos) y gris para las dimensiones.

**Click-to-filter**: clickear la barra de "Diego López" en "Top
vendedores" cambió la URL a
`?filtros={"f_vendedor":["Diego López"]}` y el dashboard entero pasó de
3.000 a 261 ventas ($ 48.320.028 → $ 4.759.224).

**Estado gris, con ese filtro de vendedor activo**: el popover de
"Sucursal" mostró **Oeste** limpio y **Centro**/**Norte** con
"(sin datos)" — Diego López pertenece a Oeste en los datos de prueba, así
que es exactamente lo esperable.

**El asistente aplica un filtro** (con el filtro de vendedor ya sacado):
`"Aplicá el filtro de medio de pago efectivo"` →

```json
{"texto":"Listo, apliqué el filtro de medio de pago en \"Efectivo\".",
 "acciones":[{"herramienta":"aplicar_filtro",
              "entrada":{"filtro":"f_medio","valor":["Efectivo"]},
              "resultado":"Filtro 'Medio de pago' aplicado."}]}
```
El dashboard bajó a 983 ventas / $ 16.932.232, coherente con "solo pagos
en efectivo".

**Métricas con un filtro propio** (verificado en una corrida separada, el
mismo día que se construyó, documentada en detalle en `HISTORIAL.md`):
se creó "Ventas en efectivo" (`suma(ventas.importe)` filtrado por
`medios_pago.nombre = Efectivo`, un camino inseguro resuelto con EXISTS)
desde el wizard, y en el chat, sin mencionar nada de esa métrica, se
probó el pedido textual exacto de Sd — *"quiero agregar un grafico de
torta ventas en efectivo por vendedor"* — y el asistente creó el gráfico
correcto usándola, con números verificados contra la API.

## Checklist

| # | Criterio | Cómo se comprueba | Estado |
|---|---|---|---|
| 1 | Clickear un gráfico filtra el dashboard entero | Corrida de referencia arriba (Diego López, 3.000 → 261 ventas); `tests/test_dashboard_api.py`, `Grafico.tsx` | ✅ |
| 2 | El asistente puede aplicar un filtro que ya existe, sin crear una versión nueva | Corrida de referencia arriba (`aplicar_filtro`); `tests/test_herramientas.py::test_herramienta_aplicar_filtro_valida_y_no_toca_la_base` | ✅ |
| 3 | El asistente puede crear filtros y gráficos nuevos con lenguaje natural (pedido original de Sd, punto 1) | Corrida "torta ventas en efectivo por vendedor" (ver `HISTORIAL.md`, paso "métricas con un filtro propio") | ✅ |
| 4 | Una métrica puede llevar su propio filtro, incluyendo caminos del lado "muchos" (opción más potente, elegida por Sd) | `ExpresionAgregacion.filtros`, EXISTS en el compilador; 8 tests de compilador + 2 de validación + 1 de edición | ✅ |
| 5 | Las opciones de un filtro se grisan según los OTROS filtros activos, sin sacarlas de la lista | Corrida de referencia arriba (Sucursal grisada por el filtro de Vendedor); `test_opciones_grisan_segun_los_otros_filtros_activos` | ✅ |
| 6 | Un filtro nunca se restringe a si mismo | `ContextoDashboard.filtros_sin`; mismo test de arriba, caso "propio" | ✅ |
| 7 | El modelo se puede ver como diagrama entidad-relación, con la calidad visual pedida ("profesional, agradable y elaborado") | `constructor/Diagrama.tsx`, notación pata de gallo real; 7 tests de vitest para el layout | ✅ |
| 8 | Ninguna pieza de esta fase rompió lo que ya andaba (fases 1 a 3) | Suite completa de backend (356 tests) y frontend (17 de vitest + build) en verde | ✅ |
| 9 | Todo reproducible en Docker, sin dejar rastro en la demo | Ver "Cómo reproducir"; 3 organizaciones descartables creadas y borradas por SQL crudo durante toda la fase, demo (workspace 1) sin tocar | ✅ |
| 10 | CLAUDE.md e HISTORIAL.md al día por pieza | Actualizados en cada commit de la fase | ✅ |

## Tests

356 tests de backend en verde por archivo, más 1 en vivo deselected
(`test_llm_en_vivo.py`). Build de frontend sin errores de TypeScript; 17
tests de vitest (7 de antes de la fase 4, más 3 del dictado por voz —
fase 3 tardía — y 7 del layout del diagrama).

## Pendientes conocidos (no bloquean la aceptación)

- **Estado gris completo**: los gráficos todavía no se pintan en gris,
  solo las opciones de los filtros de lista (alcance elegido por Sd via
  `AskUserQuestion`: "opciones de filtro primero"). Los filtros de tipo
  `rango_fecha` tampoco se restringen por los otros activos (su mínimo y
  máximo siguen siendo globales).
- **Sin propagación completa por el grafo ni cache por combinación de
  filtros**, como imaginaba originalmente la especificación (§6): se
  resolvió con una consulta directa por pedido (universo + una consulta
  extra si hay otros filtros activos), sin un módulo `asociativo/`
  separado ni cache. Funciona bien a la escala de los datos de prueba;
  si el volumen de datos reales de Sd lo justifica, se puede revisar.
- Reglas circulares del asociativo (spec §"Riesgos": *"Relaciones
  circulares en el asociativo"*) no aplican todavía: el modelo semántico
  ya prohíbe ciclos en las relaciones desde el paso 4, así que ese riesgo
  específico no puede darse con el modelo actual.
- Pendientes heredados de fases anteriores, sin relación con esta:
  vendorear las fuentes de Google Fonts, partir el bundle de JS (906 KB).

## Fase 3, todavía sin aceptación formal

Un aparte que no es de esta fase pero conviene dejar anotado: la fase 3
quedó "lista para que Sd la acepte" en `docs/fase3-aceptacion.md`
(2026-09-12) pero Sd nunca dijo "acepto" explícitamente — el trabajo
siguió directo hacia la fase 4 a pedido suyo. Si Sd quiere, esta
aceptación de la fase 4 puede cubrir las dos a la vez.
