# Fase 1 — Cimientos, sin IA: checklist de aceptación

Fecha: 2026-09-09. Versión: 0.8.02. Estado: **lista para que Sd la acepte**.

Criterio de la especificación (§9): *con los 5 CSV de prueba y un modelo
escrito a mano, el dashboard muestra KPIs, 3 gráficos y explorador con
pestañas, y los filtros afectan a todo.*

## Cómo reproducir la aceptación en 5 minutos

Con Docker Desktop corriendo, desde la raíz del repo:

```bash
docker compose up --build -d
```

Esperar a que `http://localhost:8000/api/salud` responda. La primera vez,
crear la organización Demo (dentro del contenedor, contra el mismo Postgres):

```bash
docker compose exec app python scripts/crear_organizacion.py demo
```

Cargar los 5 CSV, el modelo y el spec como el constructor de la demo:

```bash
.venv/Scripts/python.exe backend/scripts/cargar_prueba.py --url http://localhost:8000
```

Abrir `http://localhost:8000` e ingresar (accesos en `CLAUDE.md`).

## Checklist

| # | Criterio | Cómo se comprueba | Estado |
|---|---|---|---|
| 1 | Los 5 CSV se ingestan con su suciedad (latin-1, BOM, `;`, coma decimal, títulos antes del encabezado, fechas en tres formatos, huérfanos) | `cargar_prueba.py` termina con 5 tareas `terminada`; `tests/test_datos_prueba.py` y `test_ingesta_*.py` | ✅ |
| 2 | Modelo semántico escrito a mano, validado contra las fuentes reales | `datos_prueba/modelo.json`; `PUT /modelo` devuelve 201; `tests/test_modelo_*.py` | ✅ |
| 3 | El único punto que genera SQL es el compilador, y no multiplica filas | `tests/test_compilador.py` (36 tests contra SQL a mano; `E-CONS-04` para combinaciones ambiguas) | ✅ |
| 4 | Dashboard desde un spec a mano: KPIs | 5 KPIs en el tablero (cifra protagonista + 4); `GET /dashboard/kpis` | ✅ |
| 5 | Tres gráficos (la spec pide 3; hay 4) | Línea por mes, barras top vendedores, barras por categoría, dona por medio de pago; "Ver tabla" en cada uno | ✅ |
| 6 | Explorador con pestañas por entidad | 4 pestañas (productos, vendedores, ventas, pagos), paginado y ordenable | ✅ |
| 7 | Los filtros afectan a todo | Con `Sucursal = Centro`: total ventas pasa de $ 48.320.028 a $ 15.345.842; KPIs, gráficos, explorador y su total cambian a la vez; `tests/test_dashboard_api.py::test_los_filtros_afectan_a_todo` | ✅ |
| 8 | Filtro sobre una entidad del lado "muchos" (medio de pago) sigue siendo correcto | Semi-join `EXISTS`; test `test_filtro_por_entidad_del_lado_muchos_usa_semi_join` | ✅ |
| 9 | Auth y roles: constructor, visualizador y plataforma | Visualizador: ve y filtra, `PUT /modelo` → 403; otra organización → 404; `tests/test_auth.py`, `test_plataforma.py`, `test_workspaces.py` | ✅ |
| 10 | Almacén y tareas detrás de interfaces con implementación local | `app/almacen/` y `app/tareas/`; tests propios | ✅ |
| 11 | Tests de ingesta y compilador desde el principio | 244 tests backend en verde por archivo + 7 de vitest | ✅ |
| 12 | Todo levanta con Docker Compose (app + postgres) | `docker compose up --build`: el entrypoint aplica Alembic, la app sirve API y frontend, `cargar_prueba.py` completa contra el contenedor | ✅ |
| 13 | CLAUDE.md con propósito, arquitectura, convenciones, estado y decisiones | Actualizado al cierre de cada paso; narrativa en `HISTORIAL.md` | ✅ |

## Lo que se agregó a pedido de Sd, fuera de la spec

- Rol `plataforma` con pantalla de altas (organizaciones, usuarios, administradores).
- Cinco CSV sintéticos generados por script mientras no estén los reales.
- Dirección visual "informe editorial con planilla de detalle" elegida entre tres bocetos.

## Lo que queda fuera de la fase 1 (y dónde entra)

| Pendiente | Fase |
|---|---|
| Perfilado, heurísticas de claves y relaciones, Claude proponiendo semántica, wizard con semáforos | 2 |
| Chat constructor, preguntas del visualizador, historial y deshacer con operaciones granulares | 3 |
| Filtrado asociativo (verde/gris), resubida con diff de esquema, texto estructurado, R2 y Render | 4 |
| Expresiones aritméticas libres entre métricas (Sd las pidió "más adelante") | 2 o 3 |
| Vendorear las fuentes (hoy Google Fonts por `<link>`) y partir el bundle (ECharts, 864 KB) | antes de producción |
| SSE para el progreso (hoy polling) | 2 |

## Deuda técnica conocida

- `cargar_prueba.py` usa `httpx` (está en `requirements-dev.txt`, no en la imagen): es una herramienta de desarrollo.
- Las opciones de un filtro `lista` no miran los otros filtros (sin asociativo hasta la fase 4).
- La pantalla de constructor es un editor JSON: la reemplazan el wizard y el chat.
