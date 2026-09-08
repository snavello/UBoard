# CLAUDE.md — UBoard

Contexto del proyecto para Claude Code. Se lee al inicio de cada sesión.
Mantenerlo corto (se carga en cada turno); la narrativa de cómo se llegó a cada
decisión va en `HISTORIAL.md`, que no se carga automático.

## Qué es
UBoard es un BI que se construye solo. El usuario sube archivos (CSV, Excel),
el sistema infiere estructura, semántica y relaciones, arma un **modelo
semántico** y desde él propone un **dashboard** (filtros, KPIs, gráficos,
explorador por pestañas), modificable por wizard o por lenguaje natural.
Especificación rectora: [`docs/especificacion-v1.md`](docs/especificacion-v1.md).
Lectura y plan de la fase 1: [`docs/fase1-lectura-y-plan.md`](docs/fase1-lectura-y-plan.md).

Principios que no se negocian: el modelo semántico es el producto (nada
referencia columnas crudas); dos artefactos declarativos versionados
(`ModeloSemantico` y `SpecDashboard`, Pydantic); un solo motor para wizard y
chat; **empezar sin IA** (la fase 1 funciona con modelo a mano).

## Stack y arquitectura
- **Backend:** FastAPI + Pydantic v2 + SQLAlchemy 2.0 (estilo `Mapped[]`, sin
  SQLModel) + Alembic. Postgres como catálogo (organizaciones, usuarios,
  fuentes, versiones de modelo y spec, tareas). DuckDB embebido para los datos.
- **Datos:** cada fuente subida se normaliza a Parquet en el almacén y se
  registra como **vista** DuckDB (no se copia a tabla). Una conexión DuckDB en
  memoria por workspace, reconstruida desde el catálogo. Resubir = reemplazar
  el Parquet; en fase 4 las vistas apuntan a `s3://`.
- **Interfaces:** `AlmacenArchivos` (local ahora, S3/R2 en fase 4) y
  `encolar_tarea` (cola local en hilo + tabla `tarea`; polling desde el
  frontend, SSE recién en fase 2).
- **Frontend:** React 19 + Vite 8 + TypeScript + ECharts 6 (directo, hook
  propio) + TanStack Query 5 + react-router 8. CSS propio con variables y CSS
  Modules, sin Tailwind ni librería de componentes. Build en
  `backend/app/estatico/`, servido por FastAPI desde el mismo origen (sin CORS
  en producción; en dev Vite en 5173 hace proxy de `/api` a 8000).
- **Auth:** propia. JWT (PyJWT, HS256) en cookie httpOnly, renovación
  deslizante, vence a los 15 minutos sin actividad. Claves PBKDF2 (stdlib).
- **Roles:** `plataforma` (usuario en la base, sin organización: da de alta
  organizaciones y usuarios desde una pantalla), `constructor` y
  `visualizador`. El visualizador no tiene rutas de escritura: no es un
  permiso que se chequea, es que la ruta no existe para él.
- **Docker Compose:** dos servicios, `app` (Dockerfile multi-stage: Node
  compila el frontend, Python corre uvicorn; el entrypoint aplica Alembic) y
  `postgres` (puerto **5433** en el host, el 5432 lo usa Mi Trabajo).
- **Python 3.12.8** (`.python-version`), venv + pip, requirements pinneados
  exactos. **Node 24 LTS** en `C:\Program Files\nodejs` (no está en el PATH de
  las shells de Claude: anteponer `export PATH="/c/Program Files/nodejs:$PATH"`).

## Estructura del repo
```
backend/
  app/
    main.py         # crea la app, monta /api y el frontend compilado
    version.py      # VERSION y FECHA_VERSION
    api/            # routers FastAPI (todo bajo /api)
    nucleo/         # config (pydantic-settings), auth, errores
    catalogo/       # tablas SQLAlchemy (tablas.py), base, sesion
    ingesta/ perfilado/ inferencia/ modelo/ consultas/ asociativo/
    dashboard/ asistente/ almacen/   # según §3 de la spec (se crean por paso)
    estatico/       # build de Vite (gitignored)
  alembic/          # migraciones; env.py toma la URL de la config de la app
  tests/            # pytest; correr por archivo
  scripts/          # CLIs (crear_organizacion.py, cargar_prueba.py, ...)
frontend/src/       # constructor/ visualizador/ compartido/
docker/             # postgres-init.sql (crea uboard_test), entrypoint.sh
datos_prueba/       # los 5 CSV + modelo.json + spec.json
docs/               # especificación, planes
```

## Convenciones
- Todo en español: código, comentarios, UI, docs, commits. Identificadores
  sin tildes ni ñ (`organizacion`, `anio`, `pestania`).
- Voz de la UI rioplatense en segunda persona ("Subí los archivos").
- Locale es-AR: `$ 1.234,56`, fechas `dd/mm/aaaa`.
- Errores que ve una persona llevan código propio (`errores.py`, patrón
  `E-AREA-NN`).
- Migraciones: el esquema lo administra Alembic, nunca `create_all` fuera de
  tests. Cambio de modelo => migración en el mismo commit.
- Tests: ingesta y compilador se prueban puros (DuckDB en memoria, sin
  Postgres). Los de API usan la base `uboard_test` del mismo contenedor
  (`DATABASE_URL_TEST`), nunca SQLite. Correr **por archivo**.
- Versionado: `backend/app/version.py`. Sube en el mismo commit: arreglos +1
  al patch; funcionalidad nueva +1 al minor y patch a 01. `FECHA_VERSION` con
  la hora real (`date "+%Y-%m-%d %H:%M"`), nunca inventada.
- Requirements pinneados exactos; `requirements-dev.txt` jamás va a la imagen.

## Decisiones tomadas (no rediscutir sin motivo)
Todas del 2026-09-08, al arrancar la fase 1 (detalle en `HISTORIAL.md`):
- Nombre definitivo **UBoard** (la spec dice AutoBI, nombre provisorio).
- `workspace` es tabla propia que pertenece a una organización; en v1 cada
  organización tiene uno solo, y las rutas ya llevan `/workspaces/{id}/`.
- Fase 1 carga el modelo semántico **entero desde JSON** (validar + nueva
  versión). Las operaciones granulares (`renombrar_campo`, etc.), historial y
  deshacer llegan con el wizard (fase 2) y el chat (fase 3); `version_modelo`
  ya nace con columnas `operacion` y `diff`.
- Constructor en fase 1: pantalla mínima (subir archivos, pegar modelo y
  spec, ver estado) + `cargar_prueba.py`.
- Rol `plataforma` con pantalla de altas desde la fase 1 (pedido de Sd).
- Métricas: agregación simple (`suma`, `conteo`, `conteo_distinto`,
  `promedio`, `minimo`, `maximo`) y `cociente` entre dos métricas. Expresiones
  aritméticas libres entre métricas: **pendiente**, Sd las quiere más adelante.
- Explorador: columnas `campo` propio o `entidad.campo` relacionado, explícito.
- Filtros de fase 1: `rango_fecha` y `lista`. Granularidades: `dia`,
  `semana`, `mes`, `trimestre`, `anio`.
- Progreso de tareas por polling; SSE en fase 2.
- Diseño: lo define Claude en el paso 7 con paleta validada (skill dataviz) y
  2 o 3 propuestas de layout antes de codear el dashboard.
- Datos de prueba: mientras no estén los 5 CSV reales de Sd, se generan
  sintéticos con suciedad típica (`scripts/generar_datos_prueba.py`).
- Sin pandas: la ingesta usa DuckDB (`sniff_csv`, `COPY TO parquet`),
  charset-normalizer para encoding, openpyxl + pyarrow para Excel.

## Estado por fase
- **Fase 1 — Cimientos, sin IA: EN CURSO.** Plan de 9 pasos en
  `docs/fase1-lectura-y-plan.md`.
  - Paso 0 (entorno y esqueleto): HECHO 2026-09-08. Repo, venv, Node, Vite +
    React + TanStack Query, FastAPI con `/api/salud` y frontend servido,
    Alembic configurado (sin tablas), Compose, Dockerfile, tests de salud.
  - Pasos 1 a 8: pendientes (catálogo y auth, almacén y tareas, ingesta,
    modelo, compilador, spec y API, frontend, integración).
- Fases 2, 3 y 4: no empezadas.

## Método de trabajo
- Preguntar antes de decidir ante cualquier ambigüedad; no asumir. Fases
  secuenciales; dentro de cada fase, pasos chicos verificados de verdad.
- Al cerrar cada paso: tests en verde, este archivo actualizado, commit, y
  resumen a Sd de qué se hizo, qué falta y qué se necesita de él.
- Poco output intermedio; resumen claro al final.
- Skills del repo: `.claude/skills/frontend-design/` (dirección visual);
  para gráficos usar el skill `dataviz` de Claude Code (validar paleta con
  `validate_palette.js`).

## Comandos útiles
- Postgres local: `docker compose up -d postgres` (crea `uboard_dev` y `uboard_test`).
- Backend: `.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000 --app-dir backend`
- Frontend dev: `cd frontend && npm run dev` (5173, proxy a 8000).
- Build frontend: `cd frontend && npm run build` (escribe `backend/app/estatico/`).
- Migraciones (desde `backend/`): `alembic upgrade head` / `alembic revision --autogenerate -m "que cambia"`.
- Tests (desde `backend/`): `for f in tests/test_*.py; do ../.venv/Scripts/python.exe -m pytest "$f" || break; done`
- Todo en Docker como producción: `docker compose up --build`.
