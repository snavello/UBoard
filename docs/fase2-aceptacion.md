# Fase 2 — Inferencia y wizard: checklist de aceptación

Fecha: 2026-09-10. Versión: 0.15.02. Estado: **lista para que Sd la acepte**.

Criterio de la especificación (§9): *subiendo los 5 CSV desde cero, el
sistema propone el modelo correcto con al menos 80 % de las relaciones
acertadas sin intervención, y el resto se resuelve en el wizard.* Criterio
propio agregado en `docs/fase2-lectura-y-plan.md` §1: *el dashboard
propuesto por Claude carga sin errores de validación y muestra al menos los
KPIs y 3 gráficos que hoy están en `spec.json` o equivalentes.*

## Cómo reproducir la aceptación

Por script, contra un servidor corriendo (local o Docker) con una
organización vacía (`crear_organizacion.py organizacion --nombre ... --constructor ...`):

```bash
.venv/Scripts/python.exe backend/scripts/cargar_prueba.py --inferir --url http://localhost:8000 \
    --email <email del constructor> --clave <su clave>
```

Sube los 5 CSV, pide la propuesta del modelo (heurísticas + Claude),
confirma todo lo que haya quedado propuesto (el equivalente automático de
revisar el wizard a mano) y pide la propuesta del dashboard. Imprime
entidades, relaciones con su confianza, y los KPIs finales.

A mano, en el navegador: `POST /fuentes` (o el botón "Subir" de Fuentes),
`POST /modelo/proponer` (botón "Proponer modelo" en Fuentes), revisar y
confirmar en la pestaña Revisión de Modelo, `POST /dashboard/proponer`
(botón "Proponer dashboard" al pie de Revisión), y ver el resultado en
Tablero.

## Corrida de referencia (2026-09-10, organización descartable, borrada al terminar)

```
Sesión como constructor@pruebaaceptacion.test, workspace 4
Subidos 5 archivos, esperando 5 tareas...
  pagos: 3269 filas · vendedores: 12 filas · productos: 40 filas
  ventas: 3000 filas · medios_pago: 6 filas
Proponiendo el modelo (heurísticas + Claude)...
  modelo versión 1: 5 entidades, 4 relaciones, 8 métricas, 2 dimensiones de tiempo
  relaciones: pagos.id_medio_pago→medios_pago.id_medio_pago (0.95)
              pagos.id_venta→ventas.id_venta (0.90)
              ventas.id_producto→productos.id_producto (0.90)
              ventas.vendedor→vendedores.id_vendedor (0.90)
  claude: usado, 15250 tokens
Confirmando todo lo propuesto (equivalente automático del wizard)...
Proponiendo el dashboard...
  dashboard versión 1 'Panel de ventas y cobros': 4 filtros, 8 KPIs, 4 gráficos, 5 pestañas
KPIs: Total ventas = 48320027.90, Total cobrado = 48320027.90, Cantidad de ventas = 3000,
Ticket promedio = 16106.68, Unidades vendidas = 10694, Cantidad de pagos = 3269,
Cuotas promedio = 2.00, Productos activos = 40
```

## Checklist

| # | Criterio | Cómo se comprueba | Estado |
|---|---|---|---|
| 1 | Los 5 CSV se ingestan y se perfilan | igual que la fase 1 (paso 3) + `fuente.perfil` (paso 9); 8 tests de perfilado | ✅ |
| 2 | Claves primarias: 5 de 5 sin intervención | `tests/test_heuristicas.py::test_aceptacion_claves_primarias_5_de_5`; corrida de referencia: 5 entidades con clave | ✅ |
| 3 | Relaciones: al menos 80 % sin intervención (el criterio pide 80 %; acá son 4 de 4, 100 %) | `tests/test_heuristicas.py::test_aceptacion_relaciones_4_de_4_sin_intervencion`; corrida de referencia: 4 relaciones, confianza 0.90–0.95, ninguna falsa | ✅ |
| 4 | Tipos semánticos y métricas razonables, con evidencia visible | `tests/test_heuristicas.py` (tipos), `tests/test_semantica.py` (Claude); wizard muestra el motivo de cada campo | ✅ |
| 5 | Claude aporta nombres, sinónimos, tipo hechos/dimensión y hasta 8 métricas, sin tocar claves ni relaciones | `tests/test_semantica.py`; prueba en vivo contra `claude-sonnet-5` (paso 11) | ✅ |
| 6 | Si Claude falla o no hay clave, la propuesta sigue solo con heurísticas (nunca se cae la tarea) | `tests/test_modelo_api.py::test_proponer_con_claude_falso_aplica_semantica_y_cachea` (primera corrida sin respuesta grabada) | ✅ |
| 7 | Reproponer fusiona: lo confirmado y lo rechazado no se pierde | `tests/test_fusion.py` (6 tests) | ✅ |
| 8 | Wizard con semáforo (ícono + color), confirmar/rechazar de a uno y en bloque, crear relación/métrica/dimensión a mano | Verificado en el navegador (paso 13): 23 elementos confirmados de una vez, métrica creada desde el formulario | ✅ |
| 9 | El spec inicial nunca queda vacío ni inválido, aunque Claude falle | `generar_spec_base` se prueba contra el compilador real antes de proponer cada gráfico (`tests/test_generador.py`, incluida la regresión del emparejamiento que multiplicaba filas) | ✅ |
| 10 | Claude cura el spec (protagonista, títulos, qué gráficos mostrar) sin poder cambiar a qué apunta un panel | `tests/test_spec_curacion.py`; prueba en vivo: tituló "Panel de ventas y cobros", KPI protagonista correcto ($ 48.320.028, el mismo total de la fase 1) | ✅ |
| 11 | El dashboard propuesto muestra al menos los KPIs y 3 gráficos de `spec.json` | Corrida de referencia: 8 KPIs, 4 gráficos, 5 pestañas, sin advertencias | ✅ |
| 12 | Caché de Claude por huella; auditoría de tokens | Tabla `inferencia`; segunda propuesta sobre el mismo modelo sale de la caché (0 tokens) | ✅ |
| 13 | Roles y aislamiento no se rompieron con las funciones nuevas | Suite completa (auth, plataforma, workspaces) sigue en verde | ✅ |
| 14 | CLAUDE.md e HISTORIAL.md al día por paso | Actualizados en cada commit de la fase (pasos 9 a 15) | ✅ |
| 15 | Todo reproducible por script | `cargar_prueba.py --inferir` (ver arriba) | ✅ |

## Tests

298 tests de backend en verde por archivo (`for f in tests/test_*.py; do
../.venv/Scripts/python.exe -m pytest "$f" || break; done`), más 2 pruebas
en vivo contra la API real de Anthropic (`pytest tests/test_llm_en_vivo.py
-m en_vivo`, deseleccionadas por defecto: gastan unos centavos). Build y 7
tests de frontend sin cambios.

## Costo de la API de Anthropic en esta fase

Tope acordado con Sd: USD 10. Llamadas reales hechas durante el desarrollo
(pruebas en vivo + verificaciones manuales en el navegador): del orden de
10, con pedidos de pocos miles de tokens cada uno (la muestra son 30 filas
por tabla y el perfil, nunca el dataset completo). Muy por debajo del tope;
el uso real de una organización, con caché por huella, es todavía menor
porque solo se llama cuando el modelo cambia de verdad.

## Deuda y pendientes conocidos (quedan para la fase 3, como estaba previsto)

- Chat constructor, preguntas del visualizador, historial visible y
  deshacer con operaciones granulares (las operaciones ya existen desde el
  paso 12; falta el historial navegable y el botón deshacer).
- Expresiones aritméticas libres entre métricas (Sd las pidió para la fase
  3).
- El wizard no tiene una vista para editar el spec del dashboard a mano
  todavía (sigue como JSON en "Avanzado"); tampoco hace falta para la fase 2.
- SSE para el progreso de las tareas (sigue en polling, funciona bien con
  `refetchIntervalInBackground`).

## Docker: reconstruido y verificado (2026-09-10, más tarde el mismo día)

El primer intento de `docker compose up --build` falló tres veces seguidas
por un corte de red del entorno (`npm ci` con `ECONNRESET`), no por el
código; quedaron reintentos de npm en el `Dockerfile` por las dudas. A
pedido de Sd se reintentó más tarde y **la imagen se construyó bien a la
primera**.

Al correr la aceptación dentro del contenedor apareció un bug real:
`docker-compose.yml` nunca pasaba `ANTHROPIC_API_KEY` (ni el resto de la
configuración de Claude) al contenedor `app`, así que la inferencia en
Docker quedaba siempre en modo heurístico puro, en silencio, sin avisar
que faltaba la clave. Se agregaron `ANTHROPIC_API_KEY`, `MODELO_CLAUDE`,
`FILAS_MUESTRA_LLM` y `ENVIAR_MUESTRA_LLM` al servicio `app` (mismo patrón
`${VAR:-default}` que ya usaban `SECRETO_SESION` y `ENTORNO`).

Corrida de referencia contra el contenedor, con una organización
descartable (borrada al terminar con `DELETE` directo en el Postgres del
propio compose):

```
Proponiendo el modelo (heurísticas + Claude)...
  modelo versión 3: 5 entidades, 4 relaciones, 12 métricas, 2 dimensiones de tiempo
  relaciones: pagos.id_medio_pago→medios_pago.id_medio_pago (0.95)
              pagos.id_venta→ventas.id_venta (0.90)
              ventas.id_producto→productos.id_producto (0.90)
              ventas.vendedor→vendedores.id_vendedor (0.90)
  claude: usado, 15393 tokens
Proponiendo el dashboard...
  dashboard versión 2 'Panel de ventas y cobranzas': 4 filtros, 12 KPIs, 3 gráficos, 5 pestañas
KPIs: Total ventas = 48320027.90 (= Total cobrado, cierra igual que en la fase 1), ...
```

La demo (workspace 1, `Ventas del almacén`, versión 3 del spec) siguió
intacta durante toda la prueba: mismo Postgres, misma organización, sin
tocar. **Docker queda confirmado end to end**, sin pendientes de este
punto.
