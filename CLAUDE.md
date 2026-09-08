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
    nucleo/         # config (pydantic-settings), auth (JWT + roles), errores (codigos)
    catalogo/       # tablas SQLAlchemy (tablas.py), base, sesion, operaciones (altas)
    almacen/        # AlmacenArchivos (base), AlmacenLocal, rutas, obtener_almacen
    tareas/         # registro de manejadores, ColaLocal, encolar_tarea, huerfanas
    ingesta/        # codificacion, encabezado, tipado, lector_csv/excel, procesador, tarea
    consultas/      # motor.py (DuckDB por workspace); compilador en el paso 5
    perfilado/ inferencia/ modelo/ asociativo/ dashboard/ asistente/  # se crean por paso
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
    Alembic configurado, Compose, Dockerfile, tests de salud.
  - Paso 1 (catálogo y auth): HECHO 2026-09-08 (v0.2.01). Tablas
    `organizacion`, `workspace`, `usuario` (migración `c2e453e92277`);
    `/api/auth/{login,logout,yo}`; `/api/plataforma/*` (organizaciones,
    usuarios, administradores); `/api/workspaces` con la dependencia
    `workspace_del_usuario` que aísla organizaciones; `errores.py`;
    `scripts/crear_organizacion.py`; 39 tests (auth, plataforma,
    workspaces, operaciones). Sin pantallas todavía (paso 7).
  - Paso 2 (almacén y tareas): HECHO 2026-09-08 (v0.3.01). `app/almacen/`
    (interfaz `AlmacenArchivos`, `AlmacenLocal` con escritura atómica,
    `rutas.py` con la convención `org_{id}/ws_{id}/...`, `obtener_almacen`);
    `app/tareas/` (`registrar_tarea`, `encolar_tarea`, `ColaLocal` en hilo,
    `marcar_tareas_huerfanas` al arrancar); tabla `tarea` (migración
    `6f0f88df11ef`); `GET /api/workspaces/{id}/tareas[/{tarea_id}]` para el
    polling. 33 tests nuevos (72 en total).
  - Paso 3 (ingesta): HECHO 2026-09-08 (v0.4.01). `app/ingesta/`
    (codificación, encabezado, tipado, lectores CSV y Excel, procesador,
    tarea `ingesta.procesar_archivo`); tabla `fuente` (migración
    `ff39a100be3c`); `app/consultas/motor.py` (DuckDB en memoria por
    workspace con una vista por fuente); `/api/workspaces/{id}/fuentes`
    (subir 202 + polling, listar, detalle, muestra, borrar);
    `scripts/generar_datos_prueba.py` y los 5 CSV sintéticos en
    `datos_prueba/`. 66 tests nuevos (138 en total).
  - Pasos 4 a 8: pendientes (modelo, compilador, spec y API, frontend,
    integración). Las tablas `version_modelo` y `version_spec` se crean en
    el paso que las usa, cada una con su migración.
- Fases 2, 3 y 4: no empezadas.

## Accesos de la demo local
Los crea `backend/scripts/crear_organizacion.py demo` (idempotente):
- Plataforma: admin@uboard.local / uboard-plataforma-demo
- Constructor de la organización Demo: constructor@demo.local / demo-constructor-1
- Visualizador de Demo: visualizador@demo.local / demo-visualizador-1

## Reglas de auth y tenancy (vigentes desde el paso 1)
- Todo acceso a datos pasa por `workspace_del_usuario` (api/workspaces.py):
  el workspace se busca dentro de la organización del usuario logueado;
  uno ajeno devuelve 404, nunca 403 (no se enumeran ids).
- Los routers de escritura exigen rol a nivel router
  (`dependencies=[Depends(exigir_rol(...))]`), no dentro del handler.
- Login: mismo error (E-AUTH-01) para email inexistente y clave incorrecta.
  Usuario u organización desactivados: E-AUTH-04 / E-AUTH-05, también con
  sesión ya abierta (se verifica en cada request).
- Las altas viven en `catalogo/operaciones.py`; API y scripts la comparten.
- `conftest.py` hace `alembic downgrade base` + `upgrade head` en
  `uboard_test` al inicio de cada corrida: una migración no reversible rompe
  los tests, a propósito.

## Reglas de almacén y tareas (vigentes desde el paso 2)
- Nadie toca el disco directo: todo archivo pasa por `obtener_almacen()`
  con rutas relativas validadas (`validar_ruta`: sin `..`, sin absolutas,
  solo `[A-Za-z0-9._-]`). Los nombres de archivo subidos se pasan por
  `nombre_seguro` antes de armar una ruta.
- `AlmacenLocal.guardar` escribe en un temporal y hace `os.replace`: nunca
  hay un Parquet a medias bajo el nombre final. DuckDB lee con
  `uri_para_duckdb(ruta)`, que mañana será `s3://`.
- Una tarea es una función decorada con `@registrar_tarea("area.accion")`
  que recibe `(contexto, parametros)` y devuelve el dict que queda en
  `tarea.resultado`; avisa avance con `contexto.informar(progreso, mensaje)`.
  `encolar_tarea` crea la fila (commit) y después la manda a la cola. Los
  endpoints reciben la cola con `Depends(obtener_cola)` y el almacén con
  `Depends(obtener_almacen)` para que los tests los reemplacen.
- Ninguna tarea sobrevive a un reinicio: al arrancar, lo `pendiente` o
  `corriendo` se marca `error` (E-TAREA-03). En tests está apagado
  (`RECUPERAR_TAREAS_AL_ARRANCAR=false`) y se prueba aparte.
- Las excepciones dentro de una tarea no tumban el hilo: `ErrorApp` queda
  como "E-XXX-NN: mensaje"; lo inesperado como "E-INTERNO-00 ref=..." con el
  traceback en el log.

## Reglas de ingesta (vigentes desde el paso 3)
- **Un solo camino para CSV y Excel**: los lectores dejan una tabla DuckDB
  con TODAS las columnas VARCHAR y nombres ya normalizados
  (`normalizar_nombre_columna`: `IdVenta` → `id_venta`, `Año` → `anio`); el
  tipado (`tipado.py`) decide después, igual para los dos formatos.
- **El tipado es determinista y a nivel columna**: entero, decimal (estilo
  coma `1.250,50`, punto `1250.50` o en_us `1,250.50`), fecha y fecha_hora
  (formatos mezclados, dd/mm antes que mm/dd), booleano (Si/No, true/false)
  o texto. Un tipo se adopta si ≥ 95 % de los valores distintos convierten
  (`UMBRAL_TIPADO`); los que no, quedan NULL y se cuentan en
  `esquema[].invalidos`. Nunca se descarta una fila. Códigos con ceros
  adelante (`00123`) son texto. `1`/`0` son enteros, no booleanos.
- **Encoding**: UTF-8 primero (con o sin BOM); si falla, cp1252 salvo que el
  detector vea un encoding multibyte. No creerle al detector entre codepages
  de un byte (eligió cp775 para castellano).
- **Encabezados corridos**: la tabla empieza en la primera fila con el ancho
  más frecuente del archivo (`detectar_fila_encabezado`); las filas de
  título quedan en `opciones.filas_saltadas`. Si esa fila parece datos, no
  hay encabezado y los nombres son `columna_N`.
- **DuckDB lee el CSV sin sniffer** (`auto_detect = false`, `columns`,
  `strict_mode = false`, `null_padding`): ya sabemos delimitador y
  columnas, y el sniffer falla con filas de distinto largo.
- **El Parquet tiene tipos físicos** (BIGINT, DOUBLE, DATE, TIMESTAMP,
  BOOLEAN, VARCHAR). El modelo semántico (paso 4) referencia columnas por su
  nombre normalizado y su `tipo_dato` tiene que coincidir con el del esquema.
- **Identidad de una fuente = `nombre_tabla`** dentro del workspace (stem del
  archivo normalizado; en Excel con varias hojas, `archivo_hoja`). Resubir
  con el mismo nombre_tabla REEMPLAZA Parquet y esquema en la misma fila
  (`reemplazada: true` en el resultado de la tarea); el diff de esquema es
  de la fase 4. `huella` = sha256(nombre_tabla + columnas:tipos)[:16].
- **Vistas DuckDB por workspace** (`consultas/motor.py`): una base en
  memoria por workspace con `CREATE VIEW nombre_tabla AS read_parquet(uri)`;
  se reconstruye sola si cambia la firma de las fuentes y se invalida al
  ingestar o borrar. Cada llamador pide `conexion(...)` y cierra el cursor.
- La subida responde **202 con las tareas** (una por archivo) y el original
  queda en `subidas/{token}/{nombre_seguro}` para reprocesar; el frontend
  hace polling y después lista las fuentes.

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
- Datos de demo: `.venv/Scripts/python.exe backend/scripts/crear_organizacion.py demo`
  (o `plataforma` / `organizacion` para altas puntuales; `--help`).
- Regenerar los CSV sintéticos: `.venv/Scripts/python.exe backend/scripts/generar_datos_prueba.py`
  (escribe `datos_prueba/`; ver su README para la suciedad de cada archivo).
- Tests (desde `backend/`): `for f in tests/test_*.py; do ../.venv/Scripts/python.exe -m pytest "$f" || break; done`
- Todo en Docker como producción: `docker compose up --build`.
