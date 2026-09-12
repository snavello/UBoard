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
    inferencia/     # heuristicas (claves, relaciones, tipos, metricas), llm (ClienteLLM real/falso),
                    # semantica (prompt, validacion, aplicar), fusion, tarea
    modelo/edicion.py  # operaciones granulares del wizard y el chat (§4)
    dashboard/generador.py  # spec base determinista (paso 14)
    dashboard/edicion.py    # operaciones granulares del dashboard (paso 16)
    asociativo/ asistente/  # fases 3 y 4
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
  constructor/ (Fuentes, Modelo con pestañas Revisión/Avanzado, Revision =
    wizard con semáforos)  plataforma/ (Plataforma)
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
  aritméticas libres entre métricas: desde el paso 18 de la fase 3 (`ExpresionFormula`).
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
  - Paso 10 (heurísticas): HECHO 2026-09-09 (v0.10.01). `app/inferencia/`
    (`heuristicas.py` puro: claves primarias, relaciones por inclusión de
    filas + nombre, tipos semánticos por patrón, métricas obvias,
    dimensiones de tiempo, todo con confianza y evidencia; `fusion.py`
    respeta lo confirmado/rechazado y traduce referencias a los ids que ya
    existen; `tarea.py` `inferencia.proponer_modelo`); `Campo.evidencia` y
    `Metrica.confianza` en el esquema; `guardar_version` compartido en
    `modelo/operaciones.py`; `POST /modelo/proponer` (202 + tarea); botón
    "Proponer modelo" en Fuentes con aviso y polling. Aceptación de la
    fase 2 ya cumplida en test: 5/5 claves y 4/4 relaciones sin
    intervención. 11 tests de heurísticas + 6 de fusión + 3 de API (267 en
    total).
  - Paso 11 (Claude): HECHO 2026-09-09 (v0.11.01). `anthropic==1.4.0`;
    `inferencia/llm.py` (`ClienteLLM`, `ClienteAnthropic` con
    `messages.parse` + Pydantic, `ClienteFalso`, `fijar_cliente_llm` para
    tests); `inferencia/semantica.py` (prompt de sistema rioplatense, pedido
    compacto con perfil + relaciones + muestra, `RespuestaSemantica`,
    validación contra el modelo, reintento con feedback, `aplicar_semantica`);
    tabla `inferencia` (migración `822d7c18640f`) como caché por huella y
    auditoría de tokens; `Entidad.origen`; config `ANTHROPIC_API_KEY`,
    `MODELO_CLAUDE`, `FILAS_MUESTRA_LLM`, `ENVIAR_MUESTRA_LLM`; la tarea sigue
    solo con heurísticas si Claude falla (advertencia en el resultado).
    Test en vivo `tests/test_llm_en_vivo.py` (deseleccionado por defecto)
    pasó contra `claude-sonnet-5`: ~8 k tokens de entrada, ~2,5 k de salida.
    5 tests de semántica + 1 de API (273 en total, más 1 en vivo).
  - Paso 12 (operaciones granulares): HECHO 2026-09-09 (v0.12.01).
    `app/modelo/edicion.py`: 21 operaciones tipadas (Pydantic, discriminador
    `operacion`) — renombrar/asignar tipo/sinónimos/clave primaria de
    entidad; renombrar/tipo semántico/confirmar/rechazar de campo;
    crear/confirmar/rechazar/eliminar relación; crear/editar/eliminar/
    confirmar/rechazar métrica; agregar/quitar dimensión de tiempo;
    `confirmar_todo` en bloque (por sección y opcionalmente por entidad).
    `aplicar_operacion` es pura (copia el modelo, no valida); la API
    (`POST /modelo/operaciones`) valida las tres capas de siempre y guarda
    una versión con `operacion` y `diff` (`aplicar_y_guardar`, comparte
    `guardar_version` con la carga de JSON y la propuesta heurística).
    `GET /modelo/operaciones` lista los nombres válidos. Errores nuevos
    `E-MOD-04` (operación inválida) y `E-MOD-05` (no aplicable: clave
    primaria protegida, relación duplicada, métrica usada por un cociente,
    etc.). 8 tests puros + 3 de API (296 en total).
  - Paso 13 (wizard de revisión): HECHO 2026-09-10 (v0.13.01). Tipos
    TypeScript del `ModeloSemantico` en `tipos.ts` (espejo del Pydantic);
    `compartido/componentes/Semaforo.tsx` (chip confirmado/rechazado/nivel
    de confianza, con ícono además de color); `constructor/Revision.tsx`:
    pestaña principal de Modelo (la anterior pasa a "Avanzado"), secciones
    Entidades y campos (nombre y tipo semántico editables, sinónimos,
    tipo hechos/dimensión, confirmar/rechazar por campo), Relaciones
    (evidencia en castellano, confirmar/rechazar/eliminar/crear), Métricas
    (crear/editar/confirmar/rechazar/eliminar) y Dimensiones de tiempo
    (agregar/quitar), cada una con "Confirmar todo lo verde" y un botón
    global en la cabecera. Cada acción llama `POST /modelo/operaciones`
    del paso 12. Verificado en el navegador con un modelo recién propuesto
    (sin confirmar nada): semáforos, evidencia, confirmar de a uno, en
    bloque y global, crear métrica y ver dimensiones de tiempo, todo
    generando versiones correlativas. Sin tests de componente nuevos (el
    frontend sigue verificándose a mano en el navegador, como en los pasos
    6 a 12); 7 de vitest y toda la suite backend sin cambios, en verde.
  - Paso 14 (spec inicial): HECHO 2026-09-10 (v0.14.01). `dashboard/
    generador.py` (`generar_spec_base`, determinista: un KPI por métrica
    confirmada, línea por la primera dimensión de tiempo, hasta 3 barras
    por las categorías con menos valores distintos, una pestaña de
    explorador por entidad; cada combinación métrica-dimensión se prueba
    contra el compilador real antes de proponerla, para no generar un
    gráfico que multiplique filas); `inferencia/spec.py` (Claude cura:
    protagonista, títulos, orden, qué gráficos vale la pena mostrar, nunca
    cambia a qué apunta un panel; mismo patrón de validar + reintentar +
    cachear del paso 11); `dashboard/operaciones.py` con `guardar_version`
    compartido; tarea `inferencia.proponer_spec`, `POST /dashboard/proponer`
    y botón "Proponer dashboard" al pie de Revisión, con link al Tablero.
    Un test en vivo encontró un caso real donde el generador emparejaba una
    métrica con una dimensión de otra rama del modelo y multiplicaba filas;
    quedó corregido y con test de regresión. Probado en el navegador de
    punta a punta (proponer modelo, confirmar, proponer dashboard, Claude
    lo tituló "Panel de ventas" con el KPI protagonista correcto). 8 tests
    de generador + 4 de curación + 4 de API (298 en total, más 2 en vivo).
  - Paso 15 (integración y aceptación): HECHO 2026-09-10 (v0.15.02).
    `cargar_prueba.py --inferir`: reproduce la fase 2 por script (proponer
    modelo, confirmar todo con `minimo_confianza: 0`, proponer dashboard)
    contra un servidor corriendo. Checklist con evidencia en
    [`docs/fase2-aceptacion.md`](docs/fase2-aceptacion.md): 5/5 claves,
    4/4 relaciones sin intervención, dashboard curado con 8 a 12 KPIs y 3 a
    4 gráficos según la corrida. `docker compose up --build` falló al
    principio por un corte de red del entorno (no del código); reconstruido
    y verificado de punta a punta al reintentarlo: **confirmó además un bug
    real**, `docker-compose.yml` nunca pasaba `ANTHROPIC_API_KEY` (ni el
    resto de la config de Claude) al contenedor `app`, así que la
    inferencia en Docker quedaba siempre en modo heurístico puro, en
    silencio. Corregido (v0.15.02).
  - **Fase 2 aceptada por Sd el 2026-09-10.**
- **Fase 3 — Asistente: EN CURSO.** Lectura, dudas, decisiones y plan de 7
  pasos (16 a 22) en `docs/fase3-lectura-y-plan.md`, aprobado por Sd.
  - Paso 16 (operaciones del dashboard): HECHO 2026-09-10 (v0.16.01).
    `app/dashboard/edicion.py`: 14 operaciones tipadas (mismo patrón que
    `modelo/edicion.py` del paso 12) — editar título; crear/editar/eliminar
    filtro, KPI, gráfico, pestaña del explorador; `reordenar_kpis` para
    cambiar el protagonista sin recrear nada. `POST /dashboard/operaciones`
    reusa `validar_spec` (compila cada panel) y el `guardar_version` que ya
    existía. Nuevos `E-SPEC-07` (operación inválida) y `E-SPEC-08` (no
    aplicable). Es la pieza que le va a faltar al chat constructor (paso
    20) para poder "agregar un gráfico" sin tocar el JSON. 6 tests puros +
    2 de API (306 en total).
  - Paso 17 (historial y deshacer): HECHO 2026-09-11 (v0.17.01).
    `restaurar(sesion, workspace, numero, usuario)` en `modelo/operaciones.py`
    y su espejo en `dashboard/operaciones.py`: vuelve a guardar el contenido
    de una versión vieja como versión nueva (nunca se reescribe el
    historial), revalidando por si las fuentes o el modelo cambiaron desde
    entonces. `POST /modelo/versiones/{numero}/restaurar` y `POST
    /dashboard/versiones/{numero}/restaurar`. `version_spec` gana columna
    `diff` (migración `d5e2444fad05`) y `dashboard/operaciones.calcular_diff`,
    espejo del de modelo, para que el spec tenga el mismo historial legible.
    Frontend: la lista de versiones de "Avanzado" (modelo y dashboard)
    ahora muestra el diff en una línea por colección (`compartido/diff.ts`)
    y un botón "Restaurar esta versión" en todas menos la actual. Probado
    en Docker contra la demo real: restaurar y volver a restaurar,
    contenido correcto en ambos sentidos; la demo quedó como estaba. 3
    tests nuevos (309 en total).
  - Paso 18 (expresiones aritméticas): HECHO 2026-09-11 (v0.18.01).
    `modelo/esquema.py`: `ExpresionFormula { operacion: suma|resta|
    multiplicacion|division, izquierda, derecha }`, `Operando = IdCorto |
    float | ExpresionFormula` (árbol recursivo con `model_rebuild()`);
    `Metrica.expresion` suma este tercer caso a los de siempre. Un operando
    `IdCorto` referencia otra métrica (de agregación o a su vez otra
    fórmula, nunca un cociente); anidar es o bien referenciar por id una
    métrica que ya es fórmula, o embeber una `ExpresionFormula` directa
    como operando (para el chat de la fase 3, que puede armar el árbol
    entero de una). `modelo/validacion.py`: `MOD-MET-FORMULA` nuevo
    (referencia inexistente, cociente prohibido, ciclos: mismo mecanismo de
    `vistos`/`vistas` que ya cortaba los ciclos de cociente, generalizado a
    recorrer el árbol); `metrica_efectiva` generalizada igual.
    `consultas/compilador.py`: `_recolectar_agregaciones` baja el árbol
    (incluyendo métricas-fórmula referenciadas por id) hasta las métricas de
    agregación que hay que calcular en una subconsulta; `_renderizar_formula`
    arma la expresión SQL recorriendo el árbol, expandiendo en línea las
    métricas-fórmula referenciadas (no necesitan CTE propio, son aritmética
    pura sobre lo ya agregado) y con su propio `NULLIF(..., 0)` en cada nodo
    de división. `modelo/edicion.py`: `crear_metrica`/`editar_metrica`
    aceptan el tercer tipo de expresión sin cambios en la operación misma;
    `eliminar_metrica` generaliza el chequeo de "quién me usa" (antes solo
    miraba cocientes) a también encontrar referencias dentro de fórmulas,
    embebidas o anidadas. Wizard (`Revision.tsx`): tercer tipo "Fórmula" en
    "Crear una métrica", con selector de operador y un `CampoOperando` por
    lado (métrica existente o constante numérica); anidar se hace creando
    primero la fórmula interna como métrica y usándola después como
    operando de otra (no hay editor de árbol completo, como estaba
    decidido). Probado en Docker con una organización descartable: creada
    `margen = total_ventas − total_pagado` y anidada `margen_doble = margen
    × 2`, confirmadas en el wizard, y verificado el valor real vía KPI del
    dashboard (compilado y ejecutado contra Postgres/DuckDB, no solo
    validado). 9 tests nuevos (318 en total).
  - Paso 19 (motor del asistente): HECHO 2026-09-12 (v0.19.01). Antes de
    escribir código, se consultó al agente `claude-code-guide` para
    confirmar la forma vigente de tool-use multi-turno con `anthropic==1.4.0`
    (`messages.create` con `tools`; un bloque `tool_use` por herramienta
    pedida, `stop_reason == "tool_use"`; se responde con un mensaje
    `role: user` con uno o más bloques `tool_result`, `tool_use_id` +
    `content` + `is_error` opcional). `ClienteLLM` gana `conversar()`
    (un turno; el loop lo arma el llamador), con `RespuestaConversacion`
    (`bloques` crudos para reenviar como turno `assistant`, `llamadas`,
    `texto`, `es_final`); `ClienteFalso.conversar` acepta
    `respuestas_chat` (un string = texto final, una lista de
    `(nombre, entrada)` = herramientas pedidas en un turno). `app/asistente/
    herramientas.py`: una herramienta de Claude por cada una de las 35
    operaciones granulares (21 del modelo + 14 del dashboard, `input_schema`
    = `model_json_schema()` de la clase Pydantic de siempre, sin el campo
    `operacion` que ya está en el nombre), más `consultar` (de solo
    lectura, mismo `ConsultaSemantica`/compilador de siempre, con
    `filtros_base` para los filtros activos del Tablero, que el paso 21 le
    manda) y `restaurar_version` (deshacer, solo constructor).
    `catalogo_para_rol`: el visualizador solo tiene `consultar`. `app/
    asistente/motor.py`: `conversar()` arma el contexto (`armar_contexto`:
    modelo completo + dashboard actual, para que Claude sepa qué ids
    existen), corre el loop con tope `MAX_VUELTAS = 4` (si se pasa,
    `E-ASI-02`), ejecuta cada herramienta pedida y le devuelve el resultado
    o el error (`ErrorApp` se traduce a `tool_result` con `is_error: true`,
    la conversación sigue). `POST /workspaces/{id}/asistente/mensajes`: un
    solo endpoint para constructor y visualizador (`E-ASI-04` sin clave de
    Claude configurada); no persiste la conversación, solo lo que cada
    herramienta deja como versión nueva. Probado en vivo: "creá un gráfico
    de barras del total de ventas por sucursal" creó el gráfico correcto
    (32 k tokens de entrada por los 37 esquemas de herramientas), y "¿cuántas
    ventas hubo en total?" contestó bien usando `consultar`. 23 tests
    nuevos (341 en total).
  - Paso 20 (chat del constructor): HECHO 2026-09-12 (v0.20.01).
    `frontend/src/asistente/Chat.tsx`: un botón flotante ("💬 Asistente")
    que abre un panel, montado en `Marco` (visible solo si
    `usuario.rol === "constructor"`, así que aparece en cualquier pantalla
    sin tocar cada página). Cada mensaje llama a `POST
    /workspaces/{id}/asistente/mensajes` (paso 19) de forma independiente
    (no hay historial server-side, según lo decidido); el historial que se
    ve en el panel vive solo en el estado de React de esa pestaña. Por cada
    acción aplicada se muestra el resumen que devuelve la herramienta con
    un ✓ y un link a "Ver en el Tablero" o "Ver en Modelo" según si la
    operación fue del dashboard o del modelo (`OPERACIONES_DASHBOARD`,
    lista fija en el frontend, espejo de la de `dashboard/edicion.py`); si
    hubo alguna acción, se invalidan las queries de `modelo` y `dashboard`
    para que la pantalla que esté abierta se refresque sola. Verificado en
    Docker con una organización descartable: "agregá un gráfico de ventas
    por sucursal por mes" — el gráfico cruza dos dimensiones, que el
    compilador no soporta en un solo panel, así que Claude preguntó si
    quería la evolución mensual o el desglose por sucursal en vez de
    inventar algo; con "de sucursal, barras" creó el gráfico correcto, que
    apareció solo en el Tablero sin recargar la página. Confirmado además
    que el visualizador no ve el botón (le toca su propio cuadro de
    pregunta en el paso 21). Sin tests nuevos (frontend, se verifica en el
    navegador como el resto de las pantallas desde el paso 6); build y
    vitest sin cambios.
  - Paso 21 (preguntas del visualizador): HECHO 2026-09-12 (v0.21.01).
    `asistente/Chat.tsx` (paso 20) ganó `variante="inline"`: el mismo
    componente, sin el botón flotante ni el panel posicionado fijo, montado
    directamente en el `acciones` del Tablero (junto a `<Filtros>`),
    visible para constructor y visualizador. `POST
    /workspaces/{id}/asistente/mensajes` acepta ahora `filtros` (mismo
    `{id_filtro: valor}` que `GET /dashboard?filtros=`); la API los resuelve
    contra el spec actual con `dashboard.filtros.a_filtros_de_consulta`
    (`E-SPEC-04` si algún id no existe) y los pasa como `filtros_activos` a
    `motor.conversar`, que ya los aceptaba desde el paso 19
    (`catalogo_para_rol(..., filtros_base=...)`): la herramienta
    `consultar` los suma siempre a los que arme Claude, sin que dependa de
    que los mencione. `armar_contexto` también los recibe (crudos) para que
    la respuesta en texto los nombre cuando corresponda ("Ana Martínez
    vendió..."), aunque el filtrado real no depende de eso. Corregido en el
    camino un detalle de UI: la acción `consultar` no es una escritura, así
    que no tiene que mostrarse con el ✓ de "acción aplicada" (mostraba el
    JSON crudo de filas/columnas); ahora solo se listan las acciones que
    modifican algo. Probado en Docker: con el filtro "Vendedor: Ana
    Martínez" activo, la pregunta "¿cuánto vendió?" (sin nombrarla)
    contestó "Ana Martínez vendió $3.757.825,46 en total", el mismo número
    que sin filtrar por ese vendedor puntual pero acotado a sus ventas. 4
    tests nuevos (345 en total).
  - Paso 22 (integración y aceptación): HECHO 2026-09-12 (v0.21.02).
    Checklist con evidencia en
    [`docs/fase3-aceptacion.md`](docs/fase3-aceptacion.md): los dos casos
    de la especificación probados en Docker contra Claude real. "Agregá un
    gráfico de ventas por sucursal por mes" — el pedido cruza dos
    dimensiones, que el compilador no soporta en un panel, así que el
    asistente preguntó cuál de las dos quería en vez de inventar una
    combinación; con la respuesta creó el gráfico correcto. "¿Cuánto
    vendió Pérez en marzo?" encontró un bug real: el asistente filtraba
    por nombre exacto y "Pérez" no matcheaba "María Pérez"; se agregó una
    regla al prompt de sistema (usar `contiene` en vez de `igual` para
    nombres parciales) y quedó resuelto, incluyendo el caso honesto de "no
    hay ventas ese mes" (no inventa un número) y el caso con datos reales.
    Confirmado además que un filtro activo del Tablero se aplica a la
    respuesta aunque la pregunta no lo mencione (paso 21). 345 tests
    backend en verde; sin tests nuevos de este paso salvo la corrida de
    referencia documentada.
  - Adicional fuera del plan (pedido de Sd el mismo día): dictado por voz
    en el cuadro de preguntas, HECHO 2026-09-12 (v0.22.01).
    `asistente/vozWeb.ts` envuelve la Web Speech API del navegador
    (`SpeechRecognition`/`webkitSpeechRecognition`, sin backend); un botón
    de micrófono junto al campo de texto en las dos variantes de `Chat`,
    que solo aparece si el navegador la soporta. Dicta a `es-AR`, llena el
    campo, la persona revisa y envía como siempre (no manda solo por
    dictar). Verificado que el botón aparece en las dos variantes y que el
    click dispara el pedido de permiso de micrófono real del navegador (el
    entorno de prueba lo bloquea por sandbox, pero confirma que el camino
    llega); sin probar todavía con un micrófono real hablando de verdad.
  - **Fase 3 lista para que Sd la acepte** (no aceptada todavía).
- Fase 4: no empezada.

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

## Reglas de inferencia (vigentes desde el paso 10)
- `proponer_modelo(conexion, fuentes)` es puro: recibe `FuentePerfilada`
  (nombre_tabla, esquema, perfil) y una conexión DuckDB con una vista por
  fuente para medir inclusión; devuelve un `ModeloSemantico` donde todo es
  `origen: heuristica`, `estado: propuesta`, salvo la clave primaria de cada
  entidad, que va `confirmada` (una entidad no existe sin clave; la
  confianza igual queda en `evidencia` para el semáforo).
- Relación = inclusión por FILAS (no por distintos: un huérfano repetido no
  la tira) ≥ `UMBRAL_INCLUSION_FK` (0.95), mismo tipo, destino única.
  Confianza 0.7 + 0.2 nombre similar (difflib sobre raíces sin `id_`/plural,
  `UMBRAL_SIMILITUD_NOMBRE` 0.8) + 0.05 inclusión total − 0.25 sin nombre a
  favor. Sin nombre a favor se exige además no parecer medida y cubrir la
  mitad de las claves destino. Entre las ≥ 0.9: una por columna, una por par
  de entidades, sin ciclos (union-find); las sobrantes bajan a 0.89 con
  `evidencia.bajada_por`. Una columna con relación clara pierde sus otras
  candidatas sin nombre similar.
- Entidad `hechos` = tiene alguna relación saliente ≥ 0.9; si no, `dimension`.
  Métricas obvias: conteo de la clave por entidad de hechos, suma de montos
  (salvo precios/tarifas) y de cantidades con nombre claro; dimensiones de
  tiempo por cada fecha de una entidad de hechos.
- Tipos semánticos dudosos quedan en 0.6 (los mira Claude en el paso 11).
- `fusionar(existente, propuesta)`: entidades por fuente, campos por
  columna de origen, relaciones por extremos, métricas por id. Lo
  `confirmada`/`rechazada` u `origen: usuario` se conserva; lo `propuesta`
  se reemplaza con evidencia fresca **sin cambiar el id del campo**; lo
  propuesto que ya no viene se descarta; los atributos de entidad se
  conservan. Antes de mezclar, las referencias de la propuesta se traducen
  a los ids existentes (`ventas.vendedor` → `ventas.id_vendedor`).
- La tarea falla con E-INF-02 (sin fuentes), E-INF-03 (fuentes sin perfil:
  resubir) o E-INF-04 (la fusión no valida: bug, nunca debería pasar).

## Reglas de las operaciones granulares (vigentes desde el paso 12)
- Una operación es un dict `{"operacion": "...", ...parámetros}` validado
  por `TypeAdapter` con discriminador (`app/modelo/edicion.py`); lo que no
  matchea una operación conocida o le faltan/sobran parámetros es
  `E-MOD-04` con el detalle campo por campo y la lista de operaciones
  válidas. `aplicar_operacion(modelo, operacion)` es pura: copia profunda,
  aplica, devuelve `(modelo, resumen)`; no valida el resultado.
- Lo que la persona toca a mano queda `origen: usuario` (entidad, campo,
  relación creada, métrica creada/editada); confirmar o rechazar cambia
  `estado`, nunca `origen` — la evidencia sigue siendo de quien lo propuso.
- Guardas de integridad (`E-MOD-05`): no se puede rechazar ni cambiar el
  tipo semántico de un campo que es clave primaria; no se puede eliminar
  una métrica que usa un cociente; `marcar_clave_primaria` fuerza
  `identificador` y `confirmada` en los campos elegidos, pero dejar la
  clave vieja como campo suelto puede romper una relación que apuntaba
  ahí (lo detecta la validación de siempre, no esta capa). `crear_relacion`
  arma el id si no viene, marca la columna origen como `clave_foranea` y
  confirma la relación; el modelo resultante todavía puede no validar
  (ciclo, tipos distintos) y ahí responde `E-MOD-01`, no `E-MOD-05`.
- `confirmar_todo`: confirma lo `propuesta` con confianza ≥ un mínimo (0.9
  por defecto) en una sección (`campos`, `relaciones`, `metricas`, `todo`)
  y opcionalmente solo de una entidad; confirmar una relación confirma
  también sus dos campos si estaban `propuesta`.
- `POST /modelo/operaciones` reusa las tres capas de validación y
  `guardar_version` (mismo mecanismo que `PUT /modelo` y la propuesta
  heurística): una operación mala no dejo rastro, ninguna versión a medias.
- El mismo patrón se repite igual para el dashboard desde el paso 16
  (`app/dashboard/edicion.py`, `E-SPEC-07`/`E-SPEC-08`, `POST
  /dashboard/operaciones`): 14 operaciones (título; filtro, KPI, gráfico,
  pestaña del explorador con crear/editar/eliminar; `reordenar_kpis`).
  `crear_*` genera el id si no viene (mismo esquema que el generador del
  paso 14: `f_`/`k_`/`g_` + el campo o la métrica); crear con un id
  repetido es `E-SPEC-08`. Esta capa NO valida contra el modelo (eso lo
  hace `validar_spec` al guardar, y ahí un panel que multiplica filas es
  `E-SPEC-01`, no un error de esta capa).

## Reglas de historial y deshacer (vigentes desde el paso 17)
- Un solo mecanismo para las dos cosas: `restaurar(numero)` vuelve a
  guardar el CONTENIDO de una versión vieja como versión nueva de mayor
  número. El historial nunca se reescribe ni se borra; "deshacer el último
  cambio" es restaurar la versión anterior a la actual, y restaurar
  cualquier otra sirve para volver más atrás sin un botón "rehacer"
  aparte (rehacer = restaurar la que tenías antes de deshacer).
- Antes de guardar, `restaurar` vuelve a correr la validación completa
  (`validar_modelo` / `validar_contenido`) contra el estado ACTUAL de
  fuentes o modelo efectivo, no contra el de cuando se creó esa versión
  vieja: si algo cambió de forma incompatible desde entonces, restaurar
  falla igual que cualquier otra operación (`E-MOD-01` / `E-SPEC-01`), no
  se cuela en silencio.
- `version_spec` tiene `diff` desde este paso (antes solo `version_modelo`
  lo tenía); `dashboard/operaciones.calcular_diff` es un espejo exacto del
  de modelo, comparando filtros/kpis/graficos por id y pestañas por
  entidad, más un caso especial para el título (`{"anterior", "nuevo"}` en
  vez de agregados/quitados/cambiados).
- Solo el constructor puede restaurar (mismo rol que edita); el
  visualizador no ve el historial en absoluto.
- Frontend: `compartido/diff.ts` (`resumirDiff`) convierte el diff crudo en
  líneas de texto (`"metricas: +total_pagado · ~ticket_promedio"`); vive en
  la lista de versiones que ya existía en "Avanzado" (paso 7), ahora con un
  botón "Restaurar esta versión" en todas menos la primera de la lista
  (que es la actual).

## Reglas de Claude en la inferencia (vigentes desde el paso 11)
- **Claude solo opina sobre lo semántico**: nombres de entidades y campos,
  tipo hechos/dimensión, sinónimos, descripciones, tipos semánticos
  **dudosos** (confianza heurística < 0.9; identificador y clave_foranea
  nunca) y la lista de métricas (reemplaza a las tentativas; todas
  `propuesta`, `origen: llm`, confianza 0.8). Claves y relaciones no se
  tocan.
- Todo pasa por `ClienteLLM` (`inferencia/llm.py`). El real usa
  `messages.parse(output_format=Pydantic)` (salida estructurada nativa) y
  convierte `anthropic.APIError` en `E-INF-01`. **Los tests nunca tocan la
  red**: `conftest.py` instala un `ClienteFalso` vacío en todos los tests
  (autouse) y la fixture `llm_falso(respuestas)` carga respuestas grabadas.
  `tests/test_llm_en_vivo.py` (marker `en_vivo`, deseleccionado en
  `pytest.ini`) se corre a mano con `-m en_vivo -s` antes de cerrar un paso
  que toque el prompt.
- El pedido (`armar_pedido`) es JSON compacto: por entidad id, fuente,
  filas, clave, campos con tipo_dato, tipo tentativo, confianza y perfil
  resumido (nulos, distintos, min/max, 5 frecuentes, patrón), la muestra
  (`FILAS_MUESTRA_LLM`, 30; vacía con `ENVIAR_MUESTRA_LLM=false`), las
  relaciones ya decididas y las métricas tentativas. Ni la clave ni las
  muestras se loguean.
- La respuesta se valida contra el modelo (`validar_respuesta`: ids
  existentes, identificador/clave_foranea intactos, métricas con campo
  existente y agregación compatible, cocientes entre métricas de la misma
  lista) y se **reintenta una vez** con los errores como feedback; a la
  segunda falla, `E-INF-05`. Cualquier `ErrorApp` de Claude deja la
  propuesta heurística y va como `claude.advertencia` en el resultado de
  la tarea; la tarea no falla por Claude.
- **Caché**: tabla `inferencia` con huella sha256(modelo + sistema +
  pedido)[:32] única por workspace; misma huella = misma respuesta sin
  llamar (resultado `claude.cache: true`, 0 tokens). Guarda tokens de
  entrada y salida para vigilar el tope de USD 10.
- `Entidad.origen` (`usuario` por defecto): la fusión conserva nombre, tipo
  y sinónimos solo si la entidad existente es del usuario; si la nombró la
  heurística o Claude, toma los de la propuesta nueva.
- Polling del frontend con `refetchIntervalInBackground: true`: la
  inferencia tarda 20 a 30 s y la gente cambia de pestaña.

## Reglas del asistente (vigentes desde el paso 19)
- **Un solo motor, dos catálogos** (`app/asistente/`): `herramientas.py`
  arma la lista de tools de Claude según el rol (`catalogo_para_rol`) y
  `motor.py` corre el loop de conversación (`conversar`). El visualizador
  solo tiene `consultar`; el constructor tiene además las 35 operaciones
  granulares (modelo + dashboard) y `restaurar_version`.
- **Una herramienta de Claude por operación**, nunca una sola con un campo
  "operación" adentro (elige mejor por nombre): el `input_schema` sale de
  `model_json_schema()` de la clase Pydantic que ya existe en
  `modelo/edicion.py` y `dashboard/edicion.py`, sacándole el campo
  `operacion` (ya está en el nombre de la herramienta). `consultar` usa el
  `model_json_schema()` de `ConsultaSemantica` tal cual: Claude arma
  exactamente lo que el compilador espera, cero traducciones intermedias.
- `ClienteLLM.conversar()` (separado de `completar()`, que sigue siendo
  para la inferencia): un solo turno (`messages.create` con `tools`),
  devuelve `RespuestaConversacion` (`bloques` crudos para reenviar tal cual
  como turno `assistant`, `llamadas` con id/nombre/entrada de cada
  `tool_use`, `texto`, `es_final` = `stop_reason != "tool_use"`). El loop
  (tope `MAX_VUELTAS = 4`, si se pasa `E-ASI-02`) lo arma `motor.conversar`,
  no el cliente: por cada llamada que pide Claude se ejecuta la herramienta
  y se responde con un `tool_result` por `tool_use_id` (varias herramientas
  en el mismo turno de Claude se responden todas juntas en un solo mensaje
  siguiente). Un `ErrorApp` de una herramienta se traduce a
  `tool_result` con `is_error: true` y el mensaje para la persona (código +
  texto): la conversación sigue, no se corta.
- `armar_contexto` manda el modelo completo (con estado, para poder
  confirmar/rechazar por chat) y el dashboard actual como JSON compacto en
  el primer mensaje: Claude necesita ver los ids reales antes de poder
  referenciarlos en una herramienta.
- **Filtros activos del Tablero** (paso 21): `POST .../asistente/mensajes`
  acepta `filtros` (mismo `{id_filtro: valor}` de `GET /dashboard?filtros=`);
  la API los resuelve contra el spec actual (`E-SPEC-04` si algún id no
  existe) y se los pasa a `motor.conversar` como `filtros_activos`, que
  termina en `filtros_base` de la herramienta `consultar`: se suman
  SIEMPRE a los filtros que arme Claude, en el compilador, así que una
  pregunta la responde bien aunque Claude no repita el filtro por su
  cuenta. También van (crudos) en `armar_contexto`, solo para que la
  respuesta en texto pueda nombrarlos.
- **No se persiste la conversación** (decisión de la fase 3): lo único que
  queda en la base es lo que cada herramienta de escritura deja como
  versión nueva, exactamente igual que si lo hubiera hecho el wizard.
- `POST /workspaces/{id}/asistente/mensajes` es el único endpoint, para
  constructor y visualizador; el rol de la sesión decide el catálogo, el
  frontend no elige herramientas. `E-ASI-04` si no hay clave de Claude
  configurada (a diferencia de la inferencia, acá no hay "seguir sin
  Claude": el chat no existe sin él).
- Tests sin red: `ClienteFalso.conversar` acepta `respuestas_chat` (un
  string = respuesta final en texto; una lista de `(nombre, entrada)` =
  las herramientas que Claude pide en ese turno) y guarda cada turno en
  `turnos_chat` para que los tests inspeccionen qué se le mandó. Vive el
  mismo test en vivo (`test_llm_en_vivo.py`, marker `en_vivo`) que ya se
  corría antes de tocar el prompt de la inferencia.

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
  (no anidados). **Fórmula** (desde el paso 18): árbol de suma/resta/
  multiplicación/división entre operandos, cada uno un id de otra métrica
  (de agregación o de otra fórmula, nunca un cociente), una constante
  numérica o, embebida, otra `ExpresionFormula`; se valida sin ciclos
  (mismo mecanismo de `vistos` que corta la auto-referencia del cociente,
  generalizado a recorrer el árbol) y sin referenciar cocientes.

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
  **Fórmula** igual: se arma recorriendo el árbol (`_renderizar_formula`),
  expandiendo en línea cada métrica-fórmula referenciada por id (no lleva
  CTE propio, es aritmética sobre subconsultas ya agregadas) y con
  `NULLIF(..., 0)` en cada división, por anidada que esté.
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
- **Wizard de revisión** (`constructor/Revision.tsx`, paso 13): opera
  solo con las operaciones granulares del paso 12, nunca con `PUT /modelo`;
  cada botón dispara una y la vista se refresca invalidando `["modelo",
  workspaceId]`. El semáforo (`Semaforo.tsx`) nunca es solo color: un
  ícono (`✓`/`✕`/`●`/`◐`/`○`) más una palabra distinguen confirmado,
  rechazado y los tres niveles de confianza (alta ≥ 0.9, media ≥ 0.6,
  baja). La evidencia de heurísticas y Claude se traduce a una frase corta
  (`MOTIVO` para campos, inclusión/huérfanos/nombre para relaciones) en
  vez de mostrar el JSON crudo.
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
- **Chat del asistente** (`asistente/Chat.tsx`, pasos 20 y 21): un solo
  componente con dos `variante`s. `"flotante"` (por defecto): botón +
  panel que se abre y cierra, montado una sola vez en `Marco`, visible solo
  para el constructor en cualquier pantalla. `"inline"`: el cuadro de
  preguntas del Tablero (junto a `<Filtros>`, en el `acciones` de `Marco`),
  siempre visible, para constructor y visualizador, con `filtrosActivos`
  (los mismos `FiltrosActivos` de la URL) mandado como `filtros` en cada
  pedido. El historial de mensajes vive en estado de React nomás (se
  pierde al refrescar, a propósito: el backend no persiste la
  conversación); cada mensaje es un pedido independiente a `POST
  /workspaces/{id}/asistente/mensajes`. Si la respuesta trae acciones
  aplicadas, se invalidan `["modelo", workspaceId]` y `["dashboard",
  workspaceId]` (con sus `"versiones"`) para que la pantalla abierta se
  refresque sola. La acción `consultar` no se lista como "aplicada" (es de
  solo lectura, mostrar su JSON crudo era ruido): solo se muestran las que
  de verdad cambiaron algo.
- **Dictado por voz** (`asistente/vozWeb.ts`): envuelve la Web Speech API
  del navegador (`SpeechRecognition`/`webkitSpeechRecognition`, sin tipos
  oficiales de TypeScript, declarados a mano); `obtenerConstructorDeVoz()`
  devuelve `null` si el navegador no la tiene (Firefox, Safari en iOS), y
  ahí `Chat` directamente no muestra el botón de micrófono. Dicta a
  `es-AR`, llena el campo de texto (`interimResults` para ver el texto
  parcial mientras habla) y para ahí: la persona revisa y envía a mano,
  nunca se manda un mensaje solo por dictarlo.

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
  Con `--inferir`, en vez de `modelo.json`/`spec.json` pide la propuesta real
  (heurísticas + Claude) y confirma todo: es como reproducir la aceptación de
  la fase 2 por script (`docs/fase2-aceptacion.md`).
- Tests (desde `backend/`): `for f in tests/test_*.py; do ../.venv/Scripts/python.exe -m pytest "$f" || break; done`
- Tests del frontend: `cd frontend && npx vitest run` (y `npm run build` corre `tsc -b`).
- Todo en Docker como producción: `docker compose up --build`.
