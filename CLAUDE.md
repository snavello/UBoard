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
Lectura y plan de la fase 1: [`docs/fase1-lectura-y-plan.md`](docs/fase1-lectura-y-plan.md);
de la fase 2: [`docs/fase2-lectura-y-plan.md`](docs/fase2-lectura-y-plan.md).

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
    consultas/      # motor (DuckDB por workspace), esquema (ConsultaSemantica), compilador (SQL), ejecutor
    modelo/         # esquema (Pydantic), validacion (3 capas + efectivo), operaciones (versiones)
    dashboard/      # esquema del spec, validacion (compila paneles), filtros, paneles, operaciones
    perfilado/      # perfil por columna y tabla (PerfilFuente), calculado en la ingesta
    inferencia/ asociativo/ asistente/  # fases 2 a 4
    estatico/       # build de Vite (gitignored)
  alembic/          # migraciones; env.py toma la URL de la config de la app
  tests/            # pytest; correr por archivo
  scripts/          # CLIs (crear_organizacion.py, cargar_prueba.py, ...)
frontend/src/
  main.tsx App.tsx  # QueryClient, rutas por rol (Protegida), redirecciones
  tipos.ts          # espejo de los esquemas de la API
  estilos/          # tokens.css (colores claro/oscuro, tipografía, medidas), base.css
  compartido/       # api.ts (pedir, ErrorApi, 401 -> evento), sesion.tsx, formato.ts (es-AR),
                    # paleta.ts, tema.ts, filtrosUrl.ts, componentes/ (Marco, Aviso, Cargando,
                    # Pestanias, Paginador), graficos/ (useGrafico, opciones ECharts)
  paginas/Ingresar  visualizador/ (Tablero, Filtros, Kpis, Grafico, Explorador)
  constructor/ (Fuentes, Modelo)  plataforma/ (Plataforma)
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

Fase 2, del 2026-09-09 (15 dudas respondidas en `docs/fase2-lectura-y-plan.md` §7):
- Claude solo para lo semántico; claves y relaciones las deciden los datos.
  Cuenta de API de Sd con **tope de USD 10** para toda la fase: dos llamadas
  por workspace, muestra de 30 filas por tabla (`ENVIAR_MUESTRA_LLM` la apaga),
  caché por huella en tabla `inferencia` con tokens consumidos.
  `MODELO_CLAUDE` por defecto `claude-sonnet-5`. La clave la pone Sd en el
  `.env`; Claude Code nunca la escribe.
- Tests sin red (cliente LLM falso); test en vivo que se salta sin clave.
- Inferencia a pedido (botón "Proponer modelo"), con aviso al terminar las
  ingestas y botón deshabilitado mientras haya ingestas corriendo.
- Reinferir **fusiona**: respeta lo confirmado y lo rechazado.
- Todas las operaciones granulares del §4 en esta fase (`POST
  /modelo/operaciones`, una versión por operación); deshacer en la fase 3.
- El editor JSON queda como pestaña "Avanzado"; el wizard es la pantalla
  principal, con "Confirmar todo lo verde" por sección.
- Spec inicial: generador determinista curado por Claude; sin Claude se
  guarda el base.
- Sin SSE en esta fase; expresiones aritméticas libres en la fase 3.
- Umbrales: PK = 100 % únicos sin nulos; FK = inclusión ≥ 95 % + tipo igual
  + n:1, confianza 0.7 + 0.2 nombre similar + 0.05 inclusión total; solo
  ≥ 0.9 entra sin confirmar.

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
  - Paso 4 (modelo semántico): HECHO 2026-09-08 (v0.5.01). `app/modelo/`
    (esquema Pydantic del §4, validación en tres capas, modelo efectivo,
    versionado con diff); tabla `version_modelo` (migración `29bcd496a2af`);
    `/api/workspaces/{id}/modelo` (GET actual o `?efectivo=true`, PUT carga,
    POST validar, GET versiones[/{n}]); `datos_prueba/modelo.json` escrito a
    mano para los 5 CSV, validado contra sus esquemas reales. 37 tests nuevos
    (175 en total).
  - Paso 5 (compilador): HECHO 2026-09-08 (v0.6.01). `app/consultas/`
    (`esquema.py` ConsultaSemantica, `compilador.py` único generador de SQL,
    `ejecutor.py`). Camino de joins por BFS sobre el árbol, control de
    multiplicación de filas, filtros por semi-join, cocientes, granularidad,
    `entidad_base` para el explorador, orden, límite y desplazamiento. 36
    tests contra los 5 CSV comparando con SQL a mano (211 en total).
  - Paso 6 (spec y API del dashboard): HECHO 2026-09-08 (v0.7.01).
    `app/dashboard/` (esquema del §5, validación que compila cada panel,
    filtros activos, paneles como ConsultaSemantica, versionado); tabla
    `version_spec` (migración `ed7806959de1`); `/api/workspaces/{id}/dashboard`
    (spec GET/PUT/validar/versiones; `kpis`, `graficos/{id}`,
    `explorador/{entidad}` paginado, `filtros/{id}/opciones`, todos con
    `?filtros=`); `datos_prueba/spec.json`; `scripts/cargar_prueba.py`
    (carga de punta a punta contra un servidor). 26 tests nuevos (237 en
    total). **El backend de la fase 1 está completo.**
  - Paso 7 (frontend): HECHO 2026-09-08 (v0.8.01). Dirección elegida por Sd
    entre tres propuestas (lienzo `docs/disenos/propuestas-dashboard/`):
    **informe editorial con la planilla de detalle debajo**. `frontend/src/`:
    `estilos/` (tokens + base), `compartido/` (api, sesión, formato es-AR,
    paleta validada, tema, filtros en URL, componentes, `graficos/` con
    ECharts directo), `paginas/Ingresar`, `visualizador/` (Tablero, Filtros,
    Kpis, Grafico, Explorador), `constructor/` (Fuentes, Modelo con editor
    JSON de modelo y spec), `plataforma/`. Verificado en el navegador contra
    el backend real. 7 tests de vitest (formato y filtros en URL).
  - Paso 8 (integración y aceptación): HECHO 2026-09-09 (v0.8.02).
    `docker compose up --build` levanta app + postgres, el entrypoint aplica
    Alembic, `cargar_prueba.py` completa contra el contenedor y el tablero
    responde con y sin filtros como visualizador. Checklist con evidencia en
    [`docs/fase1-aceptacion.md`](docs/fase1-aceptacion.md). 244 tests
    backend + 7 de vitest.
  - **Fase 1 aceptada por Sd el 2026-09-09.**
- **Fase 2 — Inferencia y wizard: EN CURSO.** Plan de 7 pasos (9 a 15) en
  `docs/fase2-lectura-y-plan.md`.
  - Paso 9 (perfilado): HECHO 2026-09-09 (v0.9.01). `app/perfilado/`
    (`perfilar` puro sobre DuckDB, `PerfilFuente`); se calcula en la ingesta
    sobre el Parquet tipado y queda en `fuente.perfil` (migración
    `3b453523b1e8`); `GET /fuentes/{id}/perfil` (E-ING-06 si no hay);
    `perfilada` en la salida de fuente; "Ver perfil" en Fuentes. 8 tests
    puros + 2 de API (247 en total).
  - Pasos 10 a 15: pendientes.
- Fases 3 y 4: no empezadas.

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

## Reglas del perfilado (vigentes desde el paso 9)
- `perfilar(conexion, relacion, nombre_tabla, columnas)` es puro y corre
  dentro de `_tipar_y_escribir` sobre el Parquet recién escrito: una pasada
  de agregados para todas las columnas (no nulos, distintos, mín/máx en
  numéricas y temporales, promedio en numéricas, largo mín/máx en texto) y
  una consulta por columna para los 10 valores más frecuentes. Todo sale
  listo para JSON (fechas ISO, Decimal → float).
- `unica` = sin nulos y distintos == filas; `candidatas_clave` = únicas de
  tipo entero o texto (un decimal nunca es clave), en el orden del esquema.
- Patrón de texto (`email`, `url`, `numerico`, `codigo`) si lo cumple el
  90 % de hasta 200 valores distintos; sirve al tipado semántico del paso 10.
- El perfil vive en `fuente.perfil` (JSONB nullable): una fuente ingestada
  antes del paso 9 no lo tiene y el endpoint responde E-ING-06 hasta que se
  resuba. El frontend lo pide con la huella y `actualizada_en` en la clave.

## Reglas del modelo semántico (vigentes desde el paso 4)
- **Referencias**: `Entidad.fuente` = `nombre_tabla` de la fuente ingestada;
  `Campo.columna_origen` = nombre normalizado de la columna del Parquet;
  `Campo.tipo_dato` tiene que coincidir con el tipo del esquema de la
  fuente. Desde afuera un campo es `"entidad.campo"`. Ids en minúsculas
  (`^[a-z][a-z0-9_]*$`). Todo con `extra="forbid"`: una clave mal escrita
  falla al cargar.
- **Validación en tres capas**, en `modelo/validacion.py`, siempre las tres
  antes de guardar: (1) Pydantic, (2) estructura (ids únicos, PK existente y
  confirmada, relaciones a campos existentes del mismo tipo con el lado "1"
  en clave primaria, sin auto-relaciones, sin dos relaciones entre el mismo
  par, **sin ciclos** en el grafo de relaciones efectivas, métricas con
  agregación compatible, cocientes solo entre agregaciones, dimensiones de
  tiempo sobre fecha/fecha_hora, lo confirmado no depende de lo rechazado),
  (3) contra las fuentes del workspace. Cada regla tiene un código
  `MOD-...`; la API devuelve `E-MOD-01` (422) con `errores: [{codigo,
  ubicacion, mensaje}]`. `POST .../modelo/validar` corre lo mismo sin guardar.
- **Modelo efectivo** (`modelo_efectivo`): lo que ve el dashboard. Un campo o
  relación entra si está `confirmada` o `propuesta` con confianza ≥
  `umbral_confianza` (0.9); una métrica solo si está confirmada y sus campos
  o métricas entran; una relación o dimensión de tiempo cae si un campo suyo
  cae. Las entidades quedan todas; su clave primaria debe estar confirmada.
- **Versionado**: cada carga es una fila nueva en `version_modelo` con el
  modelo ENTERO (`contenido`), `numero` correlativo por workspace,
  `operacion` (`cargar_json` hoy), `diff` (ids agregados/quitados/cambiados
  por colección) y `resumen`. La versión actual es la de mayor `numero`.
- **Cociente** = numerador / denominador entre ids de métricas de agregación
  (no anidados). Las expresiones aritméticas libres siguen pendientes.

## Reglas del compilador (vigentes desde el paso 5)
- **Nadie escribe SQL fuera de `consultas/compilador.py`.** KPIs, gráficos,
  explorador, opciones de filtro y preguntas del asistente arman una
  `ConsultaSemantica` (`metricas`, `dimensiones` con granularidad y alias,
  `filtros`, `orden`, `limite`, `desplazamiento`, `entidad_base`) y llaman a
  `consultar(...)`. Se compila contra el modelo **efectivo**.
- **Cada métrica se agrega en una subconsulta que parte de SU entidad** y
  solo hace LEFT JOIN por pasos seguros (del lado "muchos" al lado "uno") hacia
  las entidades de las dimensiones. Si una dimensión exige un paso inseguro,
  la combinación multiplicaría filas y se rechaza con `E-CONS-04` (ej.
  "total_ventas por medio de pago" cuando el medio está en pagos). LEFT JOIN,
  no INNER: los huérfanos quedan en el grupo NULL y los totales cierran.
- **Filtros sobre entidades del lado "muchos" van como EXISTS** (semi-join):
  "ventas que tienen algún pago en efectivo" sí es una pregunta válida.
- **Varias entidades de métricas** = un CTE por entidad, pegados por las
  dimensiones con `IS NOT DISTINCT FROM`; sin dimensiones, CROSS JOIN de
  filas únicas. Con `entidad_base` (explorador), la lista de filas sale de
  esa entidad (todas, aunque no tengan hechos) y las métricas se pegan con
  LEFT JOIN; sin `entidad_base`, solo aparecen las combinaciones con datos.
- **Cociente** se calcula afuera: `CAST(num AS DOUBLE) / NULLIF(den, 0)`.
- **Valores de filtro siempre como parámetros `?`** con `CAST(? AS tipo)`
  según `tipo_dato`; nunca literales en el SQL. Operadores: igual, distinto,
  en, entre (extremos abiertos con null), mayor(_igual), menor(_igual),
  contiene (ILIKE), es_nulo, no_es_nulo.
- **Granularidad** solo sobre campos declarados en `dimensiones_tiempo` con
  esa granularidad (`E-CONS-05`); sale como DATE del primer día del período.
- Alias de dimensión por defecto = `"entidad.campo"`; orden por defecto =
  dimensiones ascendentes, `NULLS LAST`.

## Reglas del dashboard (vigentes desde el paso 6)
- **El spec se valida compilando cada panel** contra el modelo efectivo con
  el compilador real (sin ejecutar) y con un valor ficticio en TODOS los
  filtros del spec: un gráfico que multiplica filas o un filtro que ningún
  panel puede aplicar fallan al cargar el spec (`E-SPEC-01`, códigos
  `SPEC-*`), no al abrir el dashboard. Un gráfico sobre una fecha exige
  `granularidad`.
- **Filtros activos**: `?filtros=<JSON>` con `{id_filtro: valor}`;
  `rango_fecha` = `[desde, hasta]` (extremos abiertos con null), `lista` =
  `[valores]`. Se traducen en `dashboard/filtros.py` a filtros de consulta y
  se aplican a KPIs, gráficos, explorador y total del explorador por igual.
  Las opciones de un filtro `lista` son todos los valores del campo (sin
  asociativo hasta la fase 4); las de `rango_fecha`, mínimo y máximo.
- **Paneles** (`dashboard/paneles.py`): KPIs en UNA consulta (todas las
  métricas juntas); gráfico = una métrica por una dimensión (alias
  `dimension`), línea ordenada por la dimensión, barras y torta por la
  métrica desc con `top`; explorador = `entidad_base` de la pestaña, columnas
  propias o `entidad.campo`, con la clave primaria antepuesta como columna
  oculta (`__pk_*`) para que no se fundan filas iguales, paginado con
  `pagina`/`tamanio`, orden por alias o métrica, y `total` contado aparte.
- **El spec guarda `modelo_version`**. Si el modelo cambia después, `GET
  /dashboard` revalida y devuelve `advertencias` con los paneles rotos; esos
  paneles responden `E-CONS-01` hasta que se corrija el spec.
- Los valores salen crudos (números, fechas ISO); el frontend formatea con
  locale es-AR según `formato` (moneda, entero, decimal, porcentaje).

## Reglas del frontend (vigentes desde el paso 7)
- **Dirección visual: informe editorial** (elegida por Sd). Cabecera con
  regla gruesa, título en Newsreader (serif) y cuerpo en Source Sans 3;
  papel blanco cálido, acento violeta `--acento`; cifra protagonista grande
  (el primer KPI del spec) y el resto como cifras chicas; gráficos en orden
  de lectura (el primero a lo ancho, el resto en grilla de 2); la planilla de
  detalle (explorador) a lo ancho, debajo. Tokens en `estilos/tokens.css`,
  con modo oscuro por `prefers-color-scheme`. Sin Tailwind, sin librería de
  componentes; CSS Modules por componente y utilidades mínimas en `base.css`.
- **Gráficos con las reglas de dataviz**: ECharts directo (`echarts/core`,
  solo los módulos usados); una sola serie sin leyenda, en `--acento`;
  torta como dona con leyenda y la paleta de series validada
  (`compartido/paleta.ts`, orden fijo, no reordenar); barras ≤ 24 px con
  punta redondeada, horizontales para categorías y verticales para fechas;
  líneas de 2 px con área al 10 %; grilla hairline; textos siempre en tonos
  de tinta; tooltip con el formato de la métrica; "Ver tabla" en cada
  gráfico. El tema se lee de las variables CSS (`tema.ts`).
- **Formato es-AR en `formato.ts`**: moneda sin decimales desde $ 10.000,
  compacto en ejes (`$ 48,3 M`), fechas `dd/mm/aaaa`, períodos `ene 2026` /
  `T1 2026` / `2026`. Los valores nulos se muestran como `—` y el grupo NULL
  de un gráfico como `(sin dato)`.
- **Filtros activos en la URL** (`?filtros=<JSON>`, `filtrosUrl.ts`), mismo
  JSON que consume la API: clave de caché de TanStack Query y link
  compartible. Los chips abren un popover (lista con búsqueda y checkboxes,
  o rango con dos fechas y atajos) y aplican al instante.
- **Sesión**: `pedir()` manda `credentials: same-origin`; un 401 dispara el
  evento `uboard:sesion-vencida` y `ProveedorSesion` deja al usuario en null
  (las rutas protegidas redirigen a `/ingresar`). Al iniciar o cerrar sesión
  se descartan todas las consultas cacheadas MENOS `["yo"]`: un `clear()`
  deja al observador de `useQuery` apuntando a una consulta muerta.
- **Constructor mínimo**: Fuentes (subida múltiple con polling de tareas,
  esquema por fuente, muestra, borrar) y Modelo (editor JSON con Validar /
  Guardar versión / cargar archivo, para el modelo y para el spec, con lista
  de versiones). Lo reemplazan el wizard (fase 2) y el chat (fase 3).
- Google Fonts se carga por `<link>` en `index.html` con fallbacks
  (Georgia, Segoe UI). Pendiente vendorear las fuentes antes de producción.

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
- Cargar todo en un servidor corriendo (CSV + modelo + spec, como el constructor
  de la demo): `.venv/Scripts/python.exe backend/scripts/cargar_prueba.py [--url http://localhost:8000]`.
- Tests (desde `backend/`): `for f in tests/test_*.py; do ../.venv/Scripts/python.exe -m pytest "$f" || break; done`
- Tests del frontend: `cd frontend && npx vitest run` (y `npm run build` corre `tsc -b`).
- Todo en Docker como producción: `docker compose up --build`.
