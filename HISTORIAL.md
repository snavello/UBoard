# HISTORIAL.md — UBoard

Changelog técnico detallado. No se carga automático en cada sesión: abrirlo
cuando el trabajo puntual lo necesite. Lo vigente y corto está en `CLAUDE.md`.

## 2026-09-08 — Arranque de la fase 1, paso 0 (v0.1.01)

**Relevamiento previo.** Se leyó entera la especificación v1 y el proyecto de
referencia Mi Trabajo (CLAUDE.md, FLUJO.md, auth, skills) para copiar la forma
de trabajar. En el PC no había carpeta ni repo "UBoard" (se buscó en disco y
en GitHub); Node.js figuraba instalado por winget (24.19.0) pero no estaba en
el PATH de las shells de Claude Code; Docker Desktop instalado pero apagado.

**Las 13 preguntas y sus respuestas** (Sd, una por una):
1. Carpeta: `C:\MiTrabajoC\UBoard`.
2. Workspace: tabla propia, una por organización en v1.
3. Operaciones sobre el modelo: solo cargar JSON completo en fase 1.
4. Constructor: pantalla mínima + script de carga.
5. Sesión: 15 minutos sin actividad.
6. Altas: además del script, **rol admin de plataforma con pantalla** (no
   estaba en la spec; Sd lo pidió).
7. El admin de plataforma es un usuario en la base con rol `plataforma`.
8. Métricas: agregación + cociente ahora; expresiones aritméticas libres
   "cuando te parezca" (queda en pendientes).
9. Explorador: `campo` propio o `entidad.campo`.
10. Filtros: solo `rango_fecha` y `lista`.
11. Progreso: polling.
12. Diseño: lo define Claude y muestra propuestas.
13. Datos de prueba: generar 5 CSV sintéticos mientras llegan los reales.

Decisiones que Sd delegó ("todo lo que puedas hacer vos hacelo"): nombre
UBoard, Python 3.12.8, puerto 5433, Excel en fase 1, granularidades con
semana y trimestre, locale es-AR, voz rioplatense, versionado desde 0.1.01.

**Qué quedó armado.** Repo git en `main`; `backend/` con FastAPI (`/api/salud`,
frontend estático con fallback a `index.html` y 404 real para `/api`
desconocidas), config con pydantic-settings leyendo `.env` de la raíz,
`catalogo/` con `Base` (convención de nombres de restricciones para que las
migraciones sean reversibles) y sesión; Alembic inicializado con `env.py`
tomando la URL de la config (o `ALEMBIC_DATABASE_URL`); `frontend/` con Vite 8,
React 19, TypeScript 7, TanStack Query 5, ECharts 6 y react-router 8
instalados y el build funcionando (`tsc -b && vite build` con TypeScript 7
compila sin cambios); `docker-compose.yml` (postgres 16 en 5433 + app),
`Dockerfile` multi-stage, `docker/postgres-init.sql` (crea `uboard_test`),
`docker/entrypoint.sh`; `.claude/launch.json` con backend y frontend;
`.claude/skills/frontend-design` copiado de Mi Trabajo.

**Detalle a recordar.** Las shells de Claude Code comparten el directorio de
trabajo entre llamadas paralelas: un `cd` en una afecta a la otra. Empezar
cada comando con `cd` absoluto.

## 2026-09-08 — Fase 1, paso 1: catálogo y auth (v0.2.01)

**Tablas.** Solo las tres de tenancy y auth: `organizacion`, `workspace`
(única por organización en v1, pero tabla propia por decisión de Sd) y
`usuario`. `Base` lleva convención de nombres de restricciones para que los
downgrades sean posibles. El rol es un `Enum` NO nativo de Postgres
(VARCHAR + CHECK): agregar un rol después es una migración trivial, un enum
nativo obliga a `ALTER TYPE`. Un CHECK garantiza que solo `plataforma` va sin
organización. Las tablas de fuentes, tareas y versiones se posponen al paso
que las usa, para no migrar dos veces columnas que todavía pueden cambiar.

**Auth.** JWT (PyJWT, HS256) en cookie httpOnly `sesion_uboard`. La
renovación deslizante se hace en la dependencia `usuario_actual`, que recibe
el `Response` final y reemite la cookie (FastAPI fusiona cookies seteadas en
dependencias; no hace falta middleware). Claves PBKDF2 stdlib como Mi
Trabajo. Cookie `secure` salvo en entorno local. Fuera de local la app se
niega a arrancar con el `SECRETO_SESION` de ejemplo.

**Rol plataforma.** Pedido de Sd fuera de la spec: usuario en la base sin
organización, con su API de altas (`/api/plataforma/*`). Regla E-PLAT-05
(último admin activo) solo es alcanzable desde scripts, porque por API el
actor es siempre un admin activo y E-PLAT-08 (no desactivarse a sí mismo)
salta antes; queda probada a nivel `operaciones`.

**Aislamiento.** `workspace_del_usuario` resuelve `/workspaces/{id}` dentro
de la organización del usuario: ajeno = 404. Todas las rutas de datos de los
pasos siguientes cuelgan de esa dependencia.

**Tests.** 39, en 6 archivos, contra `uboard_test` migrando con Alembic
(downgrade base + upgrade head) al inicio de la corrida y `TRUNCATE ...
RESTART IDENTITY CASCADE` antes de cada test. `conftest.py` fuerza
`ENTORNO=local` antes de importar la app para que la cookie no sea `secure`
(el TestClient habla http). Pasaron a la primera.

**Script.** `crear_organizacion.py` con subcomandos `plataforma`,
`organizacion` y `demo` (idempotente; imprime las credenciales). Verificado
corriéndolo dos veces y con un error controlado (E-PLAT-01, salida 1).

## 2026-09-08 — Fase 1, paso 2: almacén y tareas (v0.3.01)

**Almacén.** Interfaz `AlmacenArchivos` con `guardar`, `abrir`, `leer`,
`existe`, `tamanio`, `eliminar`, `listar(prefijo)` y `uri_para_duckdb`. Las
rutas son claves relativas POSIX validadas (`validar_ruta`) y además
`AlmacenLocal` comprueba que el destino resuelto quede dentro de la raíz:
doble barrera contra nombres de archivo maliciosos. Escritura atómica
(temporal + `os.replace`). `rutas.py` fija la convención
`org_{id}/ws_{id}/fuentes/{fuente_id}.parquet` y `subidas/{fuente_id}/...`, y
`nombre_seguro` convierte "Ñandú año (marzo).xlsx" en "Nandu_ano_marzo.xlsx".
Un test escribe un Parquet real con DuckDB, lo guarda por el almacén y lo
vuelve a leer con `read_parquet` desde la URI que devuelve el almacén.

**Tareas.** Registro de manejadores por nombre (`@registrar_tarea`), tabla
`tarea` con id UUID (no se adivinan ids ajenos), estado como VARCHAR + CHECK,
`parametros`/`resultado` JSONB. `ColaLocal` es un `ThreadPoolExecutor` de 1
hilo con su propia fábrica de sesiones (en tests se le pasa la de
`uboard_test`; por eso `obtener_cola` es una dependencia y no un import).
`esperar(id)` existe para tests y scripts. No se cierra el executor en el
lifespan a propósito: los hilos no-daemon hacen que un `uvicorn` que se apaga
espere a que la ingesta en curso termine. Sí se marcan huérfanas al arrancar.

**Endpoint.** `GET /api/workspaces/{id}/tareas` y `/{tarea_id}` cuelgan de
`workspace_del_usuario`: tarea de otro workspace = 404 `E-TAREA-01`.

**Tests.** 33 nuevos (25 de almacén puros con `tmp_path`, 8 de tareas con
Postgres). Total 72. La primera corrida de `test_tareas.py` dio
`MemoryError` y las shells dejaron de poder hacer fork: fue presión de
memoria del equipo (Docker Desktop + varios Python), no del código; tras
reiniciar la sesión pasaron todos a la primera.

## 2026-09-08 — Fase 1, paso 3: ingesta (v0.4.01)

**Decisión de alcance.** La spec pone la inferencia de tipos en el perfilado
(fase 2), pero sin columnas DATE y DOUBLE reales el filtro de fechas y el
gráfico mensual de la fase 1 no funcionan. Se movió a la ingesta un **tipado
determinista** (sin IA, sin estadísticas más allá de contar) como parte de la
"normalización"; el perfilado de la fase 2 suma cardinalidad, min/max, top
valores y patrones semánticos sobre columnas ya tipadas.

**Datos sintéticos.** Como los CSV reales no estaban, Sd pidió generarlos.
`generar_datos_prueba.py` produce 3.000 ventas de un año, 3 sucursales, 12
vendedores, 40 productos, 6 medios de pago y ~3.270 pagos, con la suciedad
documentada en `datos_prueba/README.md` (latin-1, BOM, `;`, coma decimal,
títulos antes del encabezado, fechas en tres formatos, huérfanos, `$ `).
Están commiteados (240 KB) y un test los regenera en tmp y los ingesta.

**Cómo se lee un CSV.** Decodificar (UTF-8 → cp1252 → detector solo para
multibyte), detectar delimitador por el que parte más líneas en el mismo
número de campos, detectar la fila de encabezado por el ancho más frecuente,
normalizar nombres (CamelCase → snake, sin tildes, `ñ` → `ni` para que `Año`
sea `anio` y no `ano`), reescribir en UTF-8 y leer con DuckDB **sin
sniffer**. Se probó en el scratchpad: con `names=` DuckDB sigue sniffeando y
falla con filas de distinto largo; con `columns=` + `auto_detect=false` +
`strict_mode=false` + `null_padding=true` rellena las cortas y recorta las
largas. Excel entra por openpyxl (solo lectura, celdas ya tipadas pasadas a
texto canónico) y sigue el mismo camino.

**Tipado.** Decisión sobre la muestra de valores DISTINTOS de cada columna
(hasta 5.000), orden booleano → entero → decimal → fecha → texto, umbral
95 %. Detalles que costaron: `1.234` sin ninguna coma en la columna es un
decimal con punto, no mil doscientos treinta y cuatro; en la muestra de
distintos la frecuencia de formatos de fecha es por valor distinto, no por
fila (irrelevante para COALESCE, pero el test lo asumía al revés); las
fechas del test de inválidos iban del 1 al 39 de enero (bug del test, no del
código). El detector de encoding eligió cp775 (báltico) para un CSV corto en
castellano: de ahí la regla de no creerle entre codepages de un byte.

**Modelo de datos.** `fuente` con `nombre_tabla` único por workspace (la
identidad para resubir), `esquema` JSONB (nombre, nombre_origen, tipo,
nulos, invalidos, detalle), `huella`, `opciones` de lectura, `ruta_parquet`
y `ruta_original`. El motor DuckDB por workspace vive en
`consultas/motor.py` y ya lo usa la muestra; el compilador del paso 5 se
apoya en él.

**Tests.** 66 nuevos: 26 encabezado/encoding, 15 tipado (cada decisión
verificada ejecutando el SQL en DuckDB), 12 archivos (CSV sucios y Excel de
varias hojas), 6 de los datos sintéticos, 7 de la API (subida 202 + polling,
muestra, resubida que reemplaza, Excel de dos hojas, roles y aislamiento,
rechazos antes de encolar, archivo roto → tarea en error, borrado). Total
138. Además se probó en vivo contra uvicorn: los 5 CSV subidos de una con
curl como `constructor@demo.local`, las 5 tareas terminadas en 2 segundos,
tipos correctos y "Almacén"/"Azúcar" bien decodificados desde latin-1. La
organización Demo del Postgres local quedó con las 5 fuentes cargadas, listas
para el modelo a mano del paso 4.

**Ojo con los servidores de prueba.** `kill $PID` desde Git Bash NO mata un
uvicorn lanzado con `&` (el uvicorn del paso 1 siguió vivo en el 8001 y
respondió 405 a la prueba del paso 3 con código viejo). Matar por puerto con
PowerShell: `Get-NetTCPConnection -LocalPort 8002 -State Listen | % { Stop-Process -Id $_.OwningProcess -Force }`.

## 2026-09-08 — Fase 1, paso 4: modelo semántico (v0.5.01)

**Esquema.** Pydantic v2 siguiendo el §4 de la spec con tres ajustes:
`Entidad.fuente` (string = `nombre_tabla`) en lugar de `fuente_id` para no
confundirlo con el id entero de la tabla `fuente`; la expresión de métrica se
distingue por forma (`{agregacion, campo}` o `{numerador, denominador}`) sin
un campo `tipo`, así el JSON del ejemplo de la spec entra tal cual; y
`Relacion.propagar` (bool) previsto para el asociativo de la fase 4. Todo
`extra="forbid"`. Tipos de dato = los seis que produce la ingesta.

**Validación.** Tres capas separadas para que los mensajes sean precisos y
la API pueda validar sin guardar. La regla más discutible: el grafo de
relaciones efectivas tiene que ser un bosque (sin ciclos), porque con un
ciclo hay dos caminos de joins entre dos entidades y el compilador no puede
elegir; la spec lo anticipa ("relaciones circulares: se detectan y se pide
cortar"). Una relación rechazada rompe el ciclo sin borrarla. El lado "1" de
una relación tiene que ser clave primaria: si no, el join multiplica filas y
las sumas mienten. Los errores en cascada (una métrica rota arrastra al
cociente que la usa) se reportan igual: el primero es la causa.

**Bugs propios encontrados por los tests.** El detector de ciclos reportaba
el mismo ciclo dos veces porque salía del DFS al encontrarlo y el bucle
externo volvía a entrar por otra entidad de la misma componente; ahora
primero recorre la componente entera y después busca el ciclo.

**Modelo a mano.** `datos_prueba/modelo.json`: 5 entidades (ventas y pagos
como hechos), 4 relaciones n:1 que forman un árbol, 8 métricas (incluido el
`ticket_promedio` como cociente y `vendedores_activos` como conteo distinto)
y 2 dimensiones de tiempo. El test lo valida contra los esquemas reales de
los 5 CSV ingestados, y la API lo carga de verdad en Postgres.

**Tests.** 37 nuevos (31 puros de esquema/validación/efectivo/diff, 6 de
API con los 5 CSV ingestados). Total 175.

## 2026-09-08 — Fase 1, paso 5: compilador modelo → SQL (v0.6.01)

**El problema que decide el diseño: la multiplicación de filas.** En el
modelo de prueba el medio de pago cuelga de `pagos`, y una venta puede tener
dos pagos. Un join ingenuo `ventas ⟕ pagos ⟕ medios_pago` duplica el importe
de esas ventas y "total de ventas por medio de pago" da un número falso sin
que nada falle. La spec pide un dashboard cuyos filtros afecten a todo, así
que había que resolverlo bien, no evitarlo:
- Cada relación tiene un sentido seguro (del lado "muchos" al lado "uno").
  Cada métrica se agrega en una subconsulta que parte de su entidad y solo
  avanza por pasos seguros hacia las dimensiones; si necesita un paso inseguro,
  la combinación es ambigua de verdad (¿a qué medio de pago va una venta
  pagada mitad y mitad?) y se rechaza con `E-CONS-04` y un mensaje que nombra
  el paso.
- Un filtro, en cambio, sí puede cruzar un paso inseguro: "ventas que tienen
  algún pago en efectivo" está bien definido. Se compila como `EXISTS` desde
  la primera entidad del lado "muchos", con alias `__f` internos.
- Métricas de distintas entidades en la misma consulta (total ventas y total
  pagado por año) van en CTEs separados y se pegan por las dimensiones con
  `IS NOT DISTINCT FROM` sobre la unión de sus valores.
- LEFT JOIN en vez de INNER: las ventas sin vendedor o con vendedor huérfano
  no desaparecen del "top vendedores", quedan en el grupo NULL, y la suma de
  los grupos cierra con el KPI. Los tests lo comprueban.

**Explorador.** `entidad_base` cambia el origen de las filas: salen de esa
entidad (todos los productos, aunque nunca hayan vendido) y las métricas se
pegan con LEFT JOIN. Un filtro sobre otra entidad (ventas de agosto) se
aplica también a la lista base como semi-join: quedan los productos con
alguna venta en el período. `desplazamiento` + `limite` para paginar.

**Cocientes.** Sus componentes se calculan como agregaciones ocultas en sus
subconsultas y la división va afuera con `NULLIF(den, 0)`.

**Un bug que encontraron los tests.** `entidad_base` solo se resolvía cuando
había dimensiones; con una consulta de KPIs y una entidad base inexistente
no fallaba. Ahora se valida siempre.

**Tests.** 36, todos puros: DuckDB con las vistas de los 5 CSV y cada
resultado comparado con SQL escrito a mano (totales que cierran, top N,
rango de fecha, semi-join, dos entidades por la misma dimensión, explorador
paginado, valores distintos) más 14 consultas inválidas con su código y un
test de la forma exacta del SQL generado. Total 211.

## 2026-09-08 — Fase 1, paso 6: spec y API del dashboard (v0.7.01)

**Idea central: el spec se valida compilando.** Además de comprobar
referencias, cada KPI, gráfico y pestaña se arma como `ConsultaSemantica` y
se pasa por el compilador con todos los filtros del spec puestos con un valor
ficticio. Así "total de ventas por medio de pago" (multiplica filas) o un
filtro que no llega a la entidad de un panel fallan al guardar el spec, con
la ubicación del panel, y no al abrir el dashboard. El mismo módulo
`paneles.py` arma las consultas para la API: no hay dos versiones de "qué
pide un gráfico".

**Decisiones de forma.** Los filtros activos viajan en la query string como
JSON (`?filtros={"f_fecha": ["2026-01-01", null]}`) para que TanStack Query
los use como clave de cache y los GET sean compartibles por URL. El
explorador antepone la clave primaria de la entidad como columna oculta
(`__pk_*`): sin ella, dos ventas iguales se fundirían en una fila al agrupar.
Las opciones de un filtro de fecha (mínimo y máximo) se resuelven sin SQL a
mano: se agregan dos métricas efímeras al modelo en memoria y se consulta como
un KPI. El único SQL fuera del compilador es `SELECT count(*) FROM (...)` en
`ejecutor.contar`, para el total del explorador.

**Spec a mano.** 5 filtros (período, sucursal, vendedor, categoría y medio de
pago; el último cruza el paso inseguro ventas → pagos y por eso es un buen
test del semi-join), 5 KPIs, 4 gráficos (ventas por mes, top 10 vendedores,
ventas por categoría, cobros por medio de pago) y 4 pestañas del explorador.

**Script de punta a punta.** `cargar_prueba.py` (httpx) hace login, sube los
5 CSV, espera las tareas, carga modelo y spec e imprime los KPIs. Corrido
contra uvicorn sobre la organización Demo: las fuentes se reemplazaron
(`reemplazada`), el modelo quedó en versión 2 y el spec en versión 1.

**Tests.** 26 nuevos: 17 puros de esquema, validación, filtros activos y
paneles; 9 de API con todo cargado (KPIs y gráficos que cierran entre sí,
filtros que afectan a todo incluido el total del explorador, opciones,
paginado y orden, errores, spec inválido, advertencias cuando cambia el
modelo, roles y aislamiento). Total 237. Con esto el backend de la fase 1
está completo: falta el frontend (paso 7) y la aceptación (paso 8).

## 2026-09-08 — Fase 1, paso 7: frontend (v0.8.01)

**Elección de dirección.** Con el skill `design` se armó un lienzo con tres
bocetos del dashboard usando los paneles y datos reales del spec de prueba:
A "Tablero de control" (denso, barra lateral de filtros, grilla 2×2), B
"Informe editorial" (aireado, serif, cifra protagonista, gráficos en orden de
lectura, filtros como chips) y C "Planilla con tablero" (la tabla siempre a
la vista). Sd eligió **B con la planilla de detalle a lo ancho debajo**. Los
bocetos quedan en `docs/disenos/propuestas-dashboard/` (los `.dc.html` y el
`canvas.json`; el lienzo publicado es un artefacto de Claude, no se
commitea).

**Paleta.** Antes de dibujar nada se corrió `validate_palette.js` del skill
dataviz sobre las tres superficies candidatas y la oscura: la paleta de
referencia de 8 series pasa todos los controles duros (banda de luminosidad,
separación para daltonismo, piso de visión normal) en las cuatro; los
avisos de contraste (< 3:1 en amarillo, aqua y magenta sobre claro) se
resuelven con leyenda + tooltip + "Ver tabla", como pide el skill. Las
series únicas (línea, barras) usan el acento del sistema, no el slot 1, para
que gráfico y UI sean de la misma familia.

**Arquitectura del frontend.** Sin wrapper de ECharts: un hook `useGrafico`
con `echarts/core` y solo los módulos usados (aun así el bundle es de 864 KB;
partirlo con `import()` queda para más adelante). El tema de los gráficos se
lee de las variables CSS en tiempo de ejecución, así el modo oscuro del SO
los cambia sin duplicar tokens. Los filtros activos viven en la URL con el
mismo JSON que consume la API. Las páginas del constructor son mínimas a
propósito (Fuentes y un editor JSON para modelo y spec): las reemplazan el
wizard y el chat.

**Bug encontrado probando en el navegador.** Tras un login exitoso la app
volvía al formulario vacío. `iniciar()` hacía `queryClient.clear()` antes de
`setQueryData(["yo"], usuario)`: `clear()` borra la consulta a la que el
`useQuery` de `ProveedorSesion` está suscripto, el observador queda apuntando
a una consulta muerta y sigue viendo `null`; la ruta protegida redirige a
`/ingresar`, que se vuelve a montar con el estado en blanco. Se reemplazó por
`removeQueries` con un predicado que deja `["yo"]` intacta. Segundo ajuste:
la cifra protagonista ("$ 48.320.028" a 72 px) no entraba en la columna de
4/12 a 1280 px y partía el "$" en otra línea: `clamp(36px, 3.6vw, 64px)` +
`white-space: nowrap`.

**Verificado en el navegador** contra uvicorn + Postgres con la organización
Demo: login, cabecera con el título del spec, los 5 KPIs con formato es-AR,
los 4 gráficos (línea con área, barras horizontales con etiquetas, barras por
categoría con el grupo "(sin dato)", dona con leyenda), el explorador con
las 40 filas de productos. Sin errores de consola salvo el 401 esperado de
`/api/auth/yo` antes de ingresar.

**Incidente de entorno.** Al retomar la sesión, Docker Desktop no levantaba
el motor (`wsl -l -v` mostraba `docker-desktop Stopped` y `docker info`
colgaba); hizo falta matar sus procesos, `wsl --shutdown` y relanzarlo.
Además un uvicorn lanzado con `&` desde el Bash de Claude no sobrevive al
final de la llamada en esta sesión: usar `run_in_background`.

**Verificación completada al día siguiente (2026-09-09).** Con Postgres de
vuelta: filtro Sucursal = Centro desde el chip (popover con las 3 sucursales,
URL con `?filtros=`, KPI protagonista de $ 48.320.028 a $ 15.345.842, "Quitar
filtros" visible); Fuentes lista las 5 fuentes con esquema; Modelo muestra la
versión actual y el historial; Plataforma (como admin) lista organizaciones y
administradores. Un ajuste más: las cifras chicas de KPI también partían el
"$" en dos líneas en la columna angosta (`nowrap` + `clamp`).

## 2026-09-09 — Fase 1, paso 8: integración y aceptación (v0.8.02)

`docker compose up --build`: la imagen compila el frontend en la etapa de
Node y corre uvicorn en la de Python; el entrypoint aplicó las cuatro
migraciones sobre el Postgres del compose y la app respondió `/api/salud`
con la versión correcta. `cargar_prueba.py` contra el contenedor reemplazó
las 5 fuentes (los Parquet van al volumen `uboard-almacen`, no al disco
local), cargó modelo v3 y spec v2, y los KPIs cerraron (total ventas = total
pagado, como debe ser en los datos sintéticos). Como visualizador: KPIs con y
sin filtros, explorador filtrado (total 1.418 con Centro + primer semestre) y
`PUT /modelo` → 403. Suite completa en verde: 244 tests backend por archivo y
7 de vitest. El checklist con evidencia y lo que queda fuera de la fase está
en `docs/fase1-aceptacion.md`.

**Detalle a recordar.** Los Parquet viven en el almacén del proceso que
ingestó: el contenedor tiene su volumen y el uvicorn local su carpeta
`datos/almacen`. Si se alterna entre los dos contra el mismo Postgres, hay que
volver a correr `cargar_prueba.py` para que las fuentes apunten a archivos que
ese proceso pueda leer (el catálogo es uno, los archivos no).

## 2026-09-09 — Fase 1 aceptada; arranque de la fase 2

Sd aceptó la fase 1 ("ok. que sigue?") y pidió avanzar. Se presentó la
lectura, las 15 dudas, las decisiones y el plan de 7 pasos de la fase 2 en
`docs/fase2-lectura-y-plan.md`; Sd respondió las dudas de a una (resumen en
el §7 de ese documento). Lo más condicionante: tope de gasto de USD 10 en
la API de Anthropic para toda la fase, y que la clave la pone Sd en el
`.env` (Claude Code no la escribe en ningún archivo). Sd la pegó en el chat
y va a rotarla cuando termine de probar.

## 2026-09-09 — Fase 2, paso 9: perfilado (v0.9.01)

`app/perfilado/perfil.py`: `perfilar` recibe una conexión DuckDB y la
relación a leer (`read_parquet(...)` en la ingesta, una vista en tests) y
devuelve `PerfilFuente`: por columna nulos, distintos, `unica`, mín/máx,
promedio, largos, 10 valores frecuentes y patrón de texto; por tabla filas
y candidatas a clave. Se calcula en `_tipar_y_escribir` sobre el Parquet ya
tipado (así el mínimo de una fecha es una fecha y no un texto) y viaja en
`ResultadoTabla.perfil` hasta `fuente.perfil` (migración `3b453523b1e8`,
nullable para las fuentes viejas). Endpoint `GET /fuentes/{id}/perfil` y
botón "Ver perfil" en Fuentes con la tabla de estadísticas y la pastilla
"clave candidata".

Sobre los 5 CSV el perfil ya muestra la evidencia que necesita el paso 10:
`ventas.id_venta` única (candidata), `ventas.vendedor` con 96 nulos y máximo
99 (el huérfano), `productos.nombre` también única (candidata, pero segunda
en el orden), `vendedores.email` con patrón email y 3 nulos.

**Detalle.** `length()` no acepta INTEGER en DuckDB: una columna de texto
toda nula en un test de tabla armada a mano llegaba como INTEGER; se castea
a VARCHAR antes de medir el largo.

## 2026-09-09 — Fase 2, paso 10: heurísticas de claves, relaciones y tipos (v0.10.01)

`app/inferencia/heuristicas.py` arma el modelo propuesto entero desde los
perfiles y una conexión DuckDB. La primera versión medía la inclusión por
valores distintos y se perdía la relación `ventas.vendedor →
vendedores.id_vendedor`: el id huérfano 99 es un solo valor distinto entre
13 (92 %), aunque sean el 2 % de las filas. Se pasó a inclusión por filas
(98 %) y el criterio de aceptación de la fase 2 (4 de 4 relaciones, 5 de 5
claves, sin intervención) quedó cubierto por `tests/test_heuristicas.py`.

El segundo problema fue el ruido: `cantidad` (1 a 6) y `cuotas` (1 a 12)
"caben" al 100 % en cualquier tabla con ids chicos, y `pagos.id_medio_pago`
cabía también en productos, vendedores y ventas. Filtros que quedaron: sin
nombre a favor, la columna no puede parecer una medida y tiene que cubrir
al menos la mitad de las claves destino; y una columna con una relación
clara (≥ 0.9) pierde sus candidatas sin nombre similar. Con eso la
propuesta sobre los 5 CSV tiene exactamente las 4 relaciones reales.

`fusion.py` mezcla la propuesta con el modelo trabajado. Probado en el
navegador contra la demo (que tiene el modelo a mano, todo confirmado)
apareció un bug real: el modelo a mano llama `id_vendedor` al campo de la
columna `vendedor`, la propuesta lo llama `vendedor`, y la relación
propuesta apuntaba a un campo inexistente y chocaba por id con la
confirmada. Ahora la fusión traduce las referencias de la propuesta a los
ids del modelo existente antes de mezclar y desambigua ids repetidos.
Sobre la demo, reproponer produjo la versión 5 con todo lo confirmado
intacto y 4 métricas nuevas propuestas.

También: `Campo.evidencia` y `Metrica.confianza` en el esquema (defaults
compatibles con los JSON viejos), `guardar_version` compartido por la carga
de JSON y la propuesta, `POST /modelo/proponer` y el botón "Proponer
modelo" en Fuentes (deshabilitado mientras haya ingestas corriendo, con
aviso, polling y link a Modelo).

**Detalle de entorno (paso 10).** El navegador embebido perdió la cookie de sesión en
una navegación completa después del login por formulario; loguearse con
`fetch` desde la consola y recién después navegar funcionó. No es un
problema de la app (curl y los tests de API confirman el flujo).

## 2026-09-09 — Fase 2, paso 11: Claude propone la semántica (v0.11.01)

Antes de codear se consultó la forma vigente del SDK: `anthropic` 1.4.0
tiene salida estructurada nativa (`client.messages.parse(...,
output_format=ModeloPydantic)`), así que no hizo falta forzar un tool.
`ClienteLLM` es la interfaz; `ClienteAnthropic` la implementación real y
`ClienteFalso` la de los tests (respuestas grabadas, guarda los pedidos
para inspeccionar el prompt). El conftest instala el falso en TODOS los
tests: la suite jamás gasta.

El prompt de sistema fija el tono (rioplatense, nombres cortos, mayúscula
inicial) y el reparto: Claude nombra, clasifica hechos/dimensión, da
sinónimos, corrige tipos dudosos y propone entre 3 y 8 métricas; claves y
relaciones ya vienen decididas. El pedido es JSON compacto con perfil y
muestra. La respuesta se valida contra el modelo y se reintenta una vez con
los errores como feedback (§10 de la spec).

Prueba en vivo con la clave de Sd (`tests/test_llm_en_vivo.py`): pasó a la
primera contra `claude-sonnet-5` con 8.048 tokens de entrada y 2.568 de
salida. Propuso "Medios de pago", "Vendedores" con sinónimos "empleados,
personal de ventas", y 6 métricas prácticamente iguales a las del modelo
escrito a mano en la fase 1 (Total ventas, Cantidad de ventas, Ticket
promedio, Unidades vendidas, Total pagos, Vendedores activos). Desde el
navegador contra la demo (con muestra de 30 filas): 13.129 tokens de
entrada, 2.613 de salida, versión 6 del modelo con lo confirmado intacto.

**Dos cosas que aparecieron probando.** (1) Las entidades que creaba la
heurística no tenían `origen`, así que la fusión las trataba como del
usuario y no dejaba que Claude las renombrara: se agregó `Entidad.origen`.
(2) TanStack Query pausa el `refetchInterval` cuando la pestaña no está
visible; con una tarea de 30 segundos la gente cambia de pestaña y volvía a
"Analizando…" para siempre. `refetchIntervalInBackground: true` en los dos
sondeos de Fuentes.

Costo acumulado de la fase hasta acá: tres llamadas reales, unos USD 0,15.

## 2026-09-09 — Fase 2, paso 12: operaciones granulares (v0.12.01)

`app/modelo/edicion.py` tipa las 15 operaciones del §4 de la especificación
más 6 que hacían falta para que el semáforo del wizard cierre (confirmar y
rechazar campo/métrica, `confirmar_todo` en bloque): 21 en total, con
`Annotated[Union[...], Field(discriminator="operacion")]` para que Pydantic
elija la clase correcta por el nombre y reporte errores por operación. Cada
una es pura: recibe el modelo y sus parámetros, devuelve el modelo
modificado y un resumen en castellano para la versión.

La API (`POST /modelo/operaciones`) no reinventa nada: aplica la operación
sobre la versión actual y pasa por las mismas tres capas de validación y el
mismo `guardar_version` que ya usaban la carga de JSON y la propuesta
heurística, así que una operación que deja el modelo roto (por ejemplo
crear una relación que cierra un ciclo) no crea versión, igual que hoy.
Se sumaron dos códigos de error: `E-MOD-04` para una operación que no
existe o con parámetros inválidos, `E-MOD-05` para una que sintácticamente
está bien pero no se puede aplicar (rechazar la clave primaria, eliminar
una métrica que usa un cociente).

Probado a mano en `test_edicion.py` sobre el modelo escrito y sobre uno
"propuesto" armado con confianzas mixtas, para que `confirmar_todo`
tuviera algo interesante que dejar afuera. 8 tests puros y 3 de API sobre
296 en total.

## 2026-09-10 — Fase 2, paso 13: wizard de revisión con semáforos (v0.13.01)

`constructor/Revision.tsx` reemplaza al editor JSON como pestaña principal
de Modelo (que pasa a llamarse "Avanzado"). Cuatro secciones —Entidades y
campos, Relaciones, Métricas, Dimensiones de tiempo— construidas enteramente
sobre las operaciones granulares del paso 12: ningún botón del wizard llama
a `PUT /modelo`. El semáforo se decidió con ícono además de color (una
decisión que ya estaba en el plan de la fase 2, para que el rojo/verde no
sea la única señal), y la evidencia de las heurísticas se resume en una
frase ("98 % de las filas coinciden, 56 huérfanas") en vez de mostrar el
diccionario crudo.

Se probó a mano con un modelo recién propuesto (organización descartable
`PruebaWizard`, subiendo los 5 CSV y llamando a `/modelo/proponer`, con
Claude real): confirmar un campo suelto, "Confirmar lo verde" de una
entidad, el botón global "Confirmar todo lo verde" (23 elementos de una
vez), crear una métrica nueva desde el formulario y ver las dimensiones de
tiempo. Cada acción generó su versión correlativa (2 a 5) con el resumen
correcto. La organización de prueba se borró al terminar; la demo
(workspace 1) no se tocó.

Sin tests de componente nuevos: el frontend de UBoard se verifica a mano en
el navegador desde el paso 7 (vitest solo cubre utilidades puras), y este
paso sigue esa misma convención.

## 2026-09-10 — Fase 2, paso 14: spec inicial del dashboard (v0.14.01)

`app/dashboard/generador.py` arma el spec base desde el modelo efectivo: un
KPI por métrica, línea por la primera dimensión de tiempo, hasta tres
barras por las categorías más chicas, una pestaña por entidad. El test en
vivo contra Claude real (`test_llm_en_vivo.py`) encontró un bug genuino en
la primera versión: la primera dimensión de tiempo del modelo pertenecía a
`pagos` y la primera métrica a `ventas`; emparejarlas a ciegas multiplicaba
filas (`E-CONS-04`) y `validar_spec` rechazaba el spec base — justo el
spec que tiene que ser SIEMPRE válido, porque es el que se guarda si Claude
falla. La corrección: el generador ahora prueba cada combinación
métrica-dimensión contra el compilador real (`Compilador.compilar`, sin
ejecutar) y prueba con otras métricas hasta encontrar una que compile,
igual que ya hacía `validar_spec` para todo el spec completo. Quedó un
test de regresión con el caso exacto.

`app/inferencia/spec.py` cura el spec base con Claude: elige el KPI
protagonista (primero en la lista), pone títulos y etiquetas rioplatenses,
decide qué gráficos vale la pena mostrar y ordena todo. Nunca puede
cambiar a qué métrica, campo o entidad apunta un panel, ni agregar o quitar
filtros, KPIs o pestañas (solo gráficos, con `incluir: false`); mismo
mecanismo que la semántica del paso 11: validación contra el spec base,
reintento con el error como feedback, caché por huella en la tabla
`inferencia` (`tipo: "spec"`).

Probado de punta a punta en el navegador (organización descartable,
después borrada): subir los 5 CSV, proponer el modelo, "Confirmar todo lo
verde", confirmar a mano las 8 métricas (quedaron en 0.8 de confianza,
Claude nunca las auto-confirma por debajo de 0.9, a propósito) y "Proponer
dashboard". Claude tituló "Panel de ventas", puso "Total de ventas" como
protagonista ($ 48.320.028, el mismo total que en la aceptación de la fase
1) y tituló el gráfico de línea "Cobros por mes". La demo (workspace 1) no
se tocó: sigue en la versión 3 de su spec, "Ventas del almacén".

## 2026-09-10 — Fase 2, paso 15: integración y aceptación (v0.15.01)

`backend/scripts/cargar_prueba.py` gana `--inferir`: en vez de cargar
`modelo.json`/`spec.json` a mano, pide `/modelo/proponer`, confirma todo lo
que quedó propuesto con `confirmar_todo` y `minimo_confianza: 0` (el
equivalente automático de revisar el wizard), y pide `/dashboard/proponer`.
Es la forma de reproducir por script la aceptación de la fase 2, igual que
el script sin `--inferir` reproduce la de la fase 1. De paso, una
`UnicodeEncodeError` real: la consola de Windows a veces arranca en
cp1252 y el resumen de `confirmar_todo` lleva un "≥"; `sys.stdout.reconfigure
(encoding="utf-8")` al principio del script.

Corrida de referencia contra una organización descartable (borrada al
terminar): 5 entidades y 4 relaciones sin intervención (0.90 a 0.95 de
confianza, ninguna falsa), Claude usado (15.250 tokens la primera vez, caché
la segunda), dashboard "Panel de ventas y cobros" con 8 KPIs, 4 gráficos y 5
pestañas, sin advertencias. El checklist completo con la evidencia quedó en
`docs/fase2-aceptacion.md`.

**Docker no se pudo reconstruir esta sesión.** `docker compose up --build`
falló tres veces seguidas: `npm ci` cortado con `ECONNRESET` a los 30-45
segundos, siempre en la etapa del frontend (`pip`, en paralelo, sí bajaba de
PyPI sin problema). Se agregaron reintentos y timeouts más generosos a `npm
ci` en el `Dockerfile` (mejora legítima, se queda aunque no haya resuelto el
corte de esta sesión). Es un problema de red del entorno donde corrió esta
sesión, no del código de la fase 2 (el `Dockerfile` es el mismo que se
aceptó en la fase 1). Toda la verificación de este paso se hizo entonces
contra `uvicorn` local, que sirve exactamente el mismo código que la imagen.
Falta confirmar `docker compose up --build` con la red estable, de este lado
o del de Sd, antes de dar la fase 2 por cerrada del todo en Docker.

**Fase 2 completa, pendiente de la aceptación de Sd** (y de esa
confirmación en Docker).

## 2026-09-10 (más tarde) — Docker reconstruido y verificado (v0.15.02)

A pedido de Sd se reintentó `docker compose up --build`: esta vez funcionó
a la primera. Corriendo la aceptación de la fase 2 dentro del contenedor
apareció un bug real que el checklist con `uvicorn` local no podía detectar:
`docker-compose.yml` nunca pasaba `ANTHROPIC_API_KEY` (ni `MODELO_CLAUDE`,
`FILAS_MUESTRA_LLM`, `ENVIAR_MUESTRA_LLM`) al contenedor `app`. En Docker la
inferencia caía siempre a heurísticas puras, sin ningún error visible —
`obtener_cliente_llm()` devuelve `None` sin clave y la tarea sigue con
normalidad, así que nada avisaba que Claude ni se estaba llamando. Se
agregaron las cuatro variables al servicio `app` con el mismo patrón
`${VAR:-default}` que ya usaban `SECRETO_SESION` y `ENTORNO`.

Recreado el contenedor, la aceptación completa (`cargar_prueba.py
--inferir`) corrió de nuevo contra una organización descartable: 5/5 claves,
4/4 relaciones, Claude usado (15.393 tokens), dashboard "Panel de ventas y
cobranzas" con 12 KPIs y 3 gráficos, mismo total de $ 48.320.028 que en la
fase 1. La demo (workspace 1) no se tocó en ningún momento: mismo Postgres
del compose, misma organización, misma versión del spec.

`docs/fase2-aceptacion.md` y CLAUDE.md actualizados: Docker queda
confirmado end to end, sin pendientes de infraestructura para la fase 2.

## 2026-09-10 — Fase 2 aceptada; arranque de la fase 3

Sd aceptó la fase 2 ("ok fase 3"). Arranca la fase 3 (chat constructor,
preguntas del visualizador, historial y deshacer, expresiones aritméticas
libres): primero la lectura, dudas, decisiones y plan, como en las fases
anteriores.

## 2026-09-10 — Fase 3, paso 16: operaciones granulares del dashboard (v0.16.01)

`app/dashboard/edicion.py` repite exactamente el patrón de `modelo/edicion.py`
(paso 12): 14 operaciones tipadas con `TypeAdapter` discriminado por
`operacion`, puras (`aplicar_operacion(spec, operacion) -> (spec, resumen)`),
sin validar contra el modelo — eso lo sigue haciendo `validar_spec` al
guardar, compilando cada panel como siempre. `POST /dashboard/operaciones`
comparte el mismo `guardar_version` de la propuesta del paso 14, así que una
operación que deja el dashboard roto (por ejemplo, un gráfico que
multiplica filas) no crea versión.

Hoy el wizard no necesita esto: el spec sale entero del generador o del
JSON de "Avanzado". Pero es la pieza que le faltaba al plan de la fase 3
para que el chat constructor (paso 20) pueda "agregar un gráfico de ventas
por sucursal por mes" sin tocar el JSON — va a ser, literalmente, una
llamada a `crear_grafico`.

6 tests puros contra el spec escrito a mano (incluido el caso donde se crea
un gráfico con una dimensión que multiplicaría filas: la operación se
aplica igual, pero `validar_spec` la rechaza) y 2 de API. Suite completa:
306 tests backend en verde por archivo.

## 2026-09-11 — Fase 3, paso 17: historial y deshacer (v0.17.01)

Un solo mecanismo para las dos cosas, como se acordó en la duda 5 del plan
de la fase 3: `restaurar(numero)` vuelve a guardar el contenido de una
versión vieja como versión nueva, sin reescribir el historial. "Deshacer el
último cambio" es simplemente restaurar la versión anterior a la actual.
El mecanismo ya existía en germen desde el paso 12 (un comentario en
`modelo/operaciones.py` decía "el deshacer usa el contenido completo de la
version anterior, no este diff") — este paso lo hizo realidad.

Antes de guardar, `restaurar` corre la validación completa de siempre
contra el estado actual (fuentes del workspace, modelo efectivo), no
contra el de cuando se creó esa versión vieja: si algo cambió de forma
incompatible desde entonces, restaurar falla igual que cualquier otra
operación, no vuelve a colar algo roto en silencio.

`version_spec` no tenía columna `diff` (solo `version_modelo` la tenía
desde la fase 1); se agregó (`d5e2444fad05`) junto con
`dashboard/operaciones.calcular_diff`, espejo exacto del de modelo. En el
frontend, la lista de versiones que ya existía en "Avanzado" desde el paso
7 ahora muestra el diff en una línea legible por colección
(`compartido/diff.ts`) y un botón "Restaurar esta versión" en todas menos
la actual.

Probado en Docker (reconstruido sin problemas esta vez) contra el modelo
real de la demo, con ocho versiones de historial acumuladas: restaurar la
versión 1 volvió el modelo a su estado más viejo (creó la versión 9);
restaurar la versión 8 lo devolvió a como estaba antes de la prueba (creó
la versión 10, con el mismo contenido que la 8). La demo quedó exactamente
como estaba; el número de versión avanzó, que es el comportamiento
esperado — nunca se pisa el historial.

309 tests backend en verde por archivo, build y vitest del frontend sin
cambios.

## 2026-09-11 — Fase 3, paso 18: expresiones aritméticas libres (v0.18.01)

Hasta acá una métrica derivada solo podía ser un `cociente` entre dos
agregaciones. Sd las quería desde antes de arrancar la fase 1 ("Expresiones
aritméticas libres entre métricas: pendiente, Sd las quiere más adelante",
quedó anotado en las decisiones de esa fase) y las confirmó para esta fase
en la duda 7 del plan: suma, resta, multiplicación y división alcanzan, en
forma de árbol tipado — nunca una fórmula en texto libre, para poder
validarla siempre y que el chat (paso 20) nunca escriba algo que no se sepa
traducir a SQL con seguridad.

`ExpresionFormula` en `modelo/esquema.py` es un árbol recursivo
(`operacion`, `izquierda`, `derecha`), con `Operando = IdCorto | float |
ExpresionFormula` — Pydantic v2 lo resuelve con un forward ref de texto
("Operando") más `model_rebuild()` después de declarar el alias, porque el
alias y la clase se referencian entre sí. Un operando que es un id
referencia otra métrica del modelo (de agregación o, para anidar, otra
fórmula); nunca un cociente, la misma restricción que ya tenía el cociente
contra anidarse a sí mismo. Para anidar más de un nivel hay dos caminos: o
se referencia por id una métrica que ya es una fórmula guardada (lo que
hace el wizard: crear primero `margen`, después crear `margen_doble` que
usa `margen` como operando), o se embebe una `ExpresionFormula` entera como
uno de los dos operandos (pensado para el chat, que en un solo pedido de
Claude puede mandar el árbol completo sin pasar por metricas intermedias).

La validación (`_validar_formula`/`_validar_operando`) recorre el árbol
bajando por las referencias, con un `vistos: set[str]` que arranca en
`{metrica.id}` y va sumando cada id que se cruza: si un id ya está en el
set, es un ciclo (`MOD-MET-FORMULA`), directo o a través de varias métricas
intermedias. Es exactamente el mecanismo que el cociente ya usaba para no
referenciarse a sí mismo, generalizado de "un salto" a "cualquier
profundidad". `metrica_efectiva` se generalizó igual, con el mismo patrón
de `vistas` que evita el loop infinito si hay un ciclo (no debería llegar a
pasar si la validación corrió antes, pero la función no confía en eso).

El compilador tenía el mecanismo del cociente concentrado en dos lugares:
"qué hay que agregar en una subconsulta" y "qué expresión SQL armar
después de agregar". Para fórmula se generalizaron los dos:
`_recolectar_agregaciones` baja el árbol (incluyendo las métricas-fórmula
referenciadas por id, que no se agregan directo pero hay que seguir
bajando por ellas) hasta encontrar las métricas de agregación de verdad, y
`_renderizar_formula`/`_renderizar_operando` arman la expresión SQL
recorriendo el mismo árbol: una métrica-fórmula referenciada por id no
necesita su propio CTE ni JOIN, se expande en línea porque es aritmética
pura sobre columnas ya agregadas (igual filosofía que el cociente, "se
calcula afuera"). Cada nodo de división lleva su propio
`NULLIF(..., 0)`, así que una división anidada adentro de una resta no
rompe todo si el denominador da cero.

`modelo/edicion.py` no necesitó una operación nueva: `crear_metrica` y
`editar_metrica` ya recibían `expresion` como el tipo Union de siempre, se
le sumó `ExpresionFormula`. Lo que sí se generalizó fue el chequeo de
`eliminar_metrica` ("¿alguien me usa?"): antes solo miraba cocientes,
ahora también encuentra una referencia adentro de cualquier fórmula, sea
directa, anidada por id o embebida.

En el wizard (`Revision.tsx`), "Crear una métrica" suma un tercer tipo,
"Fórmula", con un select de operador y un `CampoOperando` por lado (elegir
entre "Métrica" — un select con las métricas existentes, ahí aparece
`margen` en cuanto existe — o "Número" — una constante). Anidar es
simplemente crear la fórmula interna primero y después elegirla como
operando de otra, sin editor de árbol.

Probado en Docker con una organización descartable (`PruebaFormula`, sin
`--inferir`, solo para no gastar de la cuenta de Claude): en el wizard se
creó `margen = total_ventas − total_pagado` y, anidada, `margen_doble =
margen × 2`; las dos quedaron confirmadas y con el resumen legible
esperado (`margen × 2,00`). Para no quedarse solo con la validación se
armaron además dos KPIs de dashboard apuntando a esas métricas por la API
directa y se confirmó el valor real, compilado y ejecutado contra
Postgres/DuckDB (margen ≈ 0, porque en los datos sintéticos lo pagado
coincide con lo facturado; margen_doble ≈ 2×margen), y se vio el mismo
número en el Tablero. La organización de prueba se borró al terminar.

318 tests backend en verde por archivo (9 nuevos: 8 de validación y
compilador más las extensiones a los de edición), build y vitest del
frontend sin cambios.

## 2026-09-12 — Fase 3, paso 19: motor del asistente (v0.19.01)

Antes de escribir código, tal como decía el plan de la fase 3 en la sección
de skills, se consultó al agente `claude-code-guide` para confirmar la
forma vigente de tool-use multi-turno con la versión pinneada del SDK
(`anthropic==1.4.0`): `messages.create` con `tools`, cada `tool_use` en
`response.content` con `id`/`name`/`input`, `stop_reason == "tool_use"`
para saber si hay que ejecutar algo, y la respuesta va como un mensaje
`role: user` con uno o más bloques `tool_result` (`tool_use_id` + `content`
+ `is_error` opcional) — confirmó también que el SDK no impone un tope de
vueltas automático (hay que escribir el loop a mano, que es justo lo que
hacía falta para el tope duro de 4 que pedía el plan) y que hay un "tool
runner" en beta que no convenía usar porque no da el control de logging por
operación ni el tope exacto que se necesitaba.

Con eso confirmado, el trabajo fue sobre todo de ensamblaje: casi todas las
piezas que el asistente necesita ya existían de fases anteriores
(`modelo/edicion.py` y `dashboard/edicion.py` con sus operaciones
granulares tipadas del paso 12 y 16; `consultas/esquema.py` con
`ConsultaSemantica`; el compilador). El paso 19 fue construir el puente
entre esas piezas y Claude.

`ClienteLLM` (paso 11) ganó `conversar()`, separado de `completar()` que
sigue siendo para la salida estructurada de un solo turno de la
inferencia. `conversar()` hace UN pedido y traduce la respuesta a
`RespuestaConversacion`: los bloques crudos (para reenviarlos tal cual como
el turno `assistant` siguiente, sin tener que reconstruirlos), la lista de
llamadas a herramientas que pidió, el texto si respondió, y si es una
respuesta final. El loop en sí (cuántas vueltas van, cuándo parar, qué
hacer si una herramienta falla) vive en `motor.conversar`, no en el
cliente: así el tope de vueltas y el logging de cada operación quedan en
un solo lugar, sin depender de una utilidad de más alto nivel del SDK.

`app/asistente/herramientas.py` arma el catálogo: una herramienta de
Claude por cada una de las 35 operaciones granulares que ya existían (21
del modelo, 14 del dashboard) más `consultar` (de solo lectura) y
`restaurar_version` (deshacer). El `input_schema` de cada una sale de
`model_json_schema()` de la clase Pydantic real, sacándole el campo
`operacion` (ya está en el nombre de la herramienta, pedírselo de nuevo a
Claude es redundante y podía confundir). Al pasar por `model_json_schema()`
la `ExpresionFormula` recursiva del paso 18 sale con sus `$defs` y
referencias sin problema — la documentación oficial de Anthropic acepta
JSON Schema con referencias, no hace falta aplanar nada. `consultar` usa
el `model_json_schema()` de `ConsultaSemantica` tal cual: es el mismo
contrato que ya entendía el compilador desde el paso 5, cero traducción
intermedia. El catálogo depende del rol (`catalogo_para_rol`): el
visualizador solo tiene `consultar` (con `filtros_base` ya preparado para
que la fase 21 le pase los filtros activos del Tablero sin tener que tocar
esta firma), el constructor tiene además la escritura y el deshacer.

Cuando una herramienta de escritura falla (por ejemplo, `eliminar_metrica`
sobre una métrica que no existe, o que usa un cociente), el `ErrorApp` no
corta la conversación: se traduce a un `tool_result` con `is_error: true`
y el código + mensaje para la persona, y Claude sigue con eso — puede
disculparse, preguntar de nuevo, o probar otra cosa, según el prompt de
sistema ("contale a la persona qué pasó en criollo, sin mostrar códigos
internos"). Si el visualizador (que no tiene las herramientas de escritura
en su catálogo) igual las pidiera — no debería pasar con Claude real, pero
se probó como caso defensivo — la herramienta no existe en su catálogo y
se le devuelve `E-ASI-03` como si fuera cualquier otro error de
herramienta, sin ejecutar nada.

`armar_contexto` arma el primer mensaje: el modelo completo (con estado,
para que el chat pueda confirmar/rechazar algo si hace falta) y el
dashboard actual, como JSON compacto — Claude necesita ver los ids reales
del workspace antes de poder referenciarlos en una llamada.

Se decidió, siguiendo la duda 3 ya resuelta del plan de la fase 3, no
persistir la conversación: el endpoint (`POST
/workspaces/{id}/asistente/mensajes`, uno solo para constructor y
visualizador, el rol decide el catálogo) no guarda mensajes en la base;
lo único que persiste es lo que cada herramienta de escritura deja como
versión nueva, exactamente el mismo mecanismo que si lo hubiera hecho el
wizard — el historial y el deshacer del paso 17 sirven sin cambios.

Probado en vivo contra Claude real (después de correr toda la suite de
tests para no pisar la base de tests con dos corridas de Alembic al mismo
tiempo — se probó una vez sin querer y salió "relation version_spec does
not exist" a mitad de un test, porque el `alembic downgrade base` de una
corrida le borró las tablas a la otra que estaba en el medio; no fue un
bug del código, fue correr dos pytest contra la misma base a la vez):
"Creá un gráfico de barras del total de ventas por sucursal" hizo
exactamente esa llamada a `crear_grafico` y quedó guardado como versión 2
del dashboard; "¿Cuántas ventas hubo en total?" contestó "En total hubo
3000 ventas" usando `consultar`, sin inventar el número. El pedido de
escritura gastó 32 288 tokens de entrada (el catálogo completo de 37
herramientas con sus esquemas va en cada pedido) y 171 de salida — hay que
tenerlo en cuenta para el tope de USD 10 de toda la fase, sobre todo
cuando el chat esté en uso real (paso 20) y no solo en pruebas puntuales.

23 tests nuevos: forma del catálogo por rol (puro), ejecución real de
operaciones/consultar/restaurar contra los 5 CSV cargados
(`test_herramientas.py`), el loop del motor con un `ClienteFalso`
extendido con `respuestas_chat` — texto final, una herramienta, varias
herramientas en un turno, error de herramienta que no corta la
conversación, tope de vueltas (`test_motor.py`) — y el endpoint de punta a
punta con los dos roles, sin clave configurada, sin modelo cargado, límite
de vueltas (`test_asistente_api.py`). 341 tests backend en verde (3
deselected: los dos en vivo de siempre más el nuevo de este paso).

## 2026-09-12 — Fase 3, paso 20: chat del constructor (v0.20.01)

Con el motor y el endpoint ya funcionando (paso 19), este paso fue
enteramente de frontend: un componente de chat, disponible desde cualquier
pantalla del constructor, como decía la duda 1 del plan de la fase 3
("un solo chat... disponible desde cualquier pantalla del constructor,
barra lateral o panel que se abre y cierra").

`asistente/Chat.tsx` es un botón flotante ("💬 Asistente", esquina inferior
derecha) que abre un panel. Se monta una sola vez, dentro de `Marco`
(`compartido/componentes/Marco.tsx`), el envoltorio que ya usaban todas las
páginas — así aparece en Fuentes, Modelo y Tablero sin tocar cada pantalla,
condicionado a `usuario.rol === "constructor"`.

La decisión más importante de este paso fue de diseño, no de código:
mantener la decisión de la fase 3 de "no persistir la conversación" también
en el frontend, no solo en el backend. Cada mensaje que la persona escribe
dispara un pedido completamente independiente a `POST
/workspaces/{id}/asistente/mensajes` — el backend arma el contexto desde
cero cada vez (`armar_contexto`, ya existía del paso 19) y no tiene memoria
de mensajes anteriores. El panel del chat sí muestra una lista de mensajes
(para que la persona pueda releer lo que pidió y lo que se hizo), pero esa
lista vive solo en el estado de React de esa pestaña: se pierde al
refrescar, y el backend nunca la ve como tal.

Esto tiene una consecuencia real que se verificó a propósito en la prueba:
si Claude hace una pregunta aclaratoria ("¿querés la evolución mensual o el
desglose por sucursal?") y la persona contesta con una frase corta ("de
sucursal, barras"), esa respuesta corta viaja SOLA al backend, sin la
pregunta que la motivó. Funcionó en la prueba porque Claude pudo inferir el
pedido completo con el contexto del modelo (sabe que "sucursal" es un campo
de `vendedores` y "barras" es un tipo de gráfico), pero es un límite real
del diseño actual: un pedido más elíptico ("no, el otro vendedor") podría
no tener con qué reconstruirse. Queda anotado como algo a revisar si hace
falta un chat con memoria real entre mensajes (agregaría mandar el
historial completo de bloques de Anthropic de ida y vuelta entre el
frontend y el backend, sin persistir nada en la base — technically posible
sin romper "no persistir conversación", pero no estaba pedido para este
paso y se prefirió no adelantarlo sin que Sd lo pida).

Por cada acción que el asistente aplica, se muestra el resumen que ya
devuelve la herramienta (paso 19) con un ✓, más un link "Ver en el
Tablero" o "Ver en Modelo" según si la operación tocó el dashboard o el
modelo — una lista fija en el frontend (`OPERACIONES_DASHBOARD`) que
espeja los nombres de las 14 operaciones de `dashboard/edicion.py`, para no
tener que exponer esa clasificación desde el backend solo para esto. Si
hubo alguna acción, se invalidan las queries de modelo y dashboard: la
pantalla que esté abierta se refresca sola, sin que la persona tenga que
recargar (se vio en la prueba: el gráfico nuevo apareció en el Tablero
inmediatamente después de cerrar el chat, sin tocar nada más).

Probado en Docker con una organización descartable (`PruebaChat`, borrada
al terminar): el pedido exacto de la aceptación de la fase ("agregá un
gráfico de ventas por sucursal por mes") activó la pregunta aclaratoria
correcta porque ese gráfico cruzaría dos dimensiones, algo que el
compilador no soporta en un panel — Claude no inventó un gráfico raro, hizo
la pregunta que el prompt de sistema le pide hacer ante la ambigüedad. La
respuesta "de sucursal, barras" produjo el gráfico correcto (`barras de
total_ventas por vendedores.sucursal`), visible al instante en el Tablero.
Se confirmó también que el visualizador no ve el botón del asistente (le
toca su propio cuadro de preguntas en el Tablero, paso 21).

Sin tests automáticos nuevos (frontend, se sigue verificando a mano en el
navegador, igual que el resto de las pantallas desde el paso 6); build de
Vite y vitest sin cambios (7 tests). La suite de backend no se tocó en este
paso (341 tests, sin cambios).

## 2026-09-12 — Fase 3, paso 21: preguntas del visualizador (v0.21.01)

Último paso de funcionalidad de la fase antes de la integración y
aceptación (paso 22). El plan decía "cuadro de pregunta en el Tablero
mismo, cerca de los filtros... el constructor lo tiene ahí también, además
del chat de escritura" — y "mismo componente para el chat de escritura y
el cuadro de preguntas". Con eso, el trabajo fue generalizar el `Chat.tsx`
del paso 20 en vez de escribir uno nuevo.

`Chat` ahora recibe una prop `variante` (`"flotante"`, la de siempre, o
`"inline"`) y opcionalmente `filtrosActivos`. En modo inline no hay botón
ni posición fija: se monta directamente en el `acciones` del Tablero,
justo al lado de `<Filtros>`, y queda siempre visible — no hace falta
abrirlo, porque en el Tablero "preguntar" es la acción principal, no una
utilidad secundaria. El mismo componente, dos pantallas, dos formularios,
sin duplicar la lógica de mandar el mensaje, mostrar "pensando" o listar
las acciones aplicadas.

La parte de backend fue chica porque el terreno ya estaba armado desde el
paso 19: `motor.conversar` ya aceptaba un `filtros_activos` que reenviaba
a `catalogo_para_rol(..., filtros_base=...)`, y la herramienta `consultar`
ya sabía sumarlos a los filtros que arma Claude. Lo que faltaba era la
punta que los trae desde afuera: `POST /asistente/mensajes` ahora acepta
`filtros` en el cuerpo, con el mismo formato `{id_filtro: valor}` que ya
usa `GET /dashboard?filtros=` desde la fase 1 — nada nuevo que aprender
para el frontend, es literalmente el mismo objeto `FiltrosActivos` que ya
tenía en la URL. La API los traduce a `FiltroConsulta` con
`dashboard.filtros.a_filtros_de_consulta` (la misma función que usan los
paneles del dashboard) y falla con `E-SPEC-04` si algún id de filtro ya no
existe en el spec actual.

Un detalle a propósito: los filtros van SIEMPRE a la consulta real,
aunque Claude no los mencione ni los repita en los parámetros que arma
para `consultar` — se suman en `_tool_consultar`, antes de compilar. Esto
importaba porque no hay que confiar en que Claude "se acuerde" de aplicar
el filtro: la garantía tiene que estar en el código, no en el prompt. Lo
único que depende de Claude es que la RESPUESTA EN TEXTO los mencione con
gracia (para eso se le pasan los filtros activos, crudos, en
`armar_contexto`) — pero el número siempre sale bien aunque Claude no diga
una palabra sobre el filtro.

Al probar en el navegador apareció un detalle de UI que no se había visto
antes porque el paso 20 solo probó acciones de escritura: la acción
`consultar` se mostraba en el chat con el mismo ✓ que una operación real,
pero el "resultado" de esa herramienta es el JSON crudo de columnas y
filas (pensado para que lo lea Claude, no una persona) — se veía
literalmente `{"columnas": [...], "filas": [[3757825.46, 243]]}` debajo de
la respuesta en texto, que ya decía lo mismo en criollo. Se sacó
`consultar` de la lista de "acciones aplicadas" que se muestran: esa lista
es para operaciones que cambiaron algo, no para consultas de solo lectura,
cuyo resultado ya está en el texto de la respuesta.

Probado en Docker con una organización descartable, como constructor y
como visualizador: activé el filtro "Vendedor: Ana Martínez" en el Tablero
y le pregunté "¿cuánto vendió?" sin nombrarla — contestó "Ana Martínez
vendió $3.757.825,46 en total, en 243 ventas", el número correcto para esa
persona sola. Confirmé también que el constructor ve los dos widgets a la
vez en el Tablero (el cuadro inline y el botón flotante), tal como pedía
el plan.

4 tests nuevos en el backend (filtros aplicados de verdad, filtro
inexistente da `E-SPEC-04`, sin filtros se comporta igual que antes,
`armar_contexto` los incluye cuando corresponde): 345 tests backend en
verde. Sin tests de frontend nuevos (se verifica en el navegador, como
todo el frontend desde el paso 6); build y vitest sin cambios.

## 2026-09-12 — Fase 3, paso 22: integración y aceptación (v0.21.02)

Último paso de la fase: `docs/fase3-aceptacion.md` con los dos casos
exactos de la especificación (§9) probados en Docker contra Claude real,
no simulados.

El primer caso, "agregá un gráfico de ventas por sucursal por mes", puso
en evidencia algo interesante de la propia frase: tal como está escrita
pide cruzar dos dimensiones (sucursal y mes) en un gráfico, y el
compilador nunca soportó eso — un gráfico es una métrica por UNA
dimensión, desde el paso 6. El asistente no adivinó ni promedió las dos
cosas en algo raro: preguntó cuál de las dos interpretaciones quería la
persona, exactamente como le pide el prompt de sistema ante un pedido
ambiguo. Con la respuesta ("de sucursal, en barras") creó el gráfico
correcto de verdad, visible en el Tablero. Se documentó la conversación
completa con los tokens de cada vuelta (16 e ~32 mil de entrada por
mensaje, la mayor parte es el catálogo de 37 herramientas que va siempre).

El segundo caso, "¿cuánto vendió Pérez en marzo?", encontró un bug real la
primera vez que se probó: el asistente arma un filtro `igual` para nombres
de personas, y "Pérez" no es igual a "María Pérez" — devolvió cero
resultados y le preguntó a la persona el nombre completo, un
comportamiento correcto (no inventó nada) pero que fallaba el caso más
común, justo el que pide la especificación tal cual. Se agregó una regla
al prompt de sistema (`app/asistente/motor.py`, `SISTEMA`): ante un nombre
parcial o un dato de texto que puede no calzar exacto, usar el operador
`contiene` antes que `igual`, y solo preguntar por el dato exacto si
`contiene` tampoco encuentra nada. Con la regla, "Pérez" resolvió bien a
"María Pérez" — y ahí apareció otro dato real: en la muestra sintética,
esa vendedora no tuvo ventas en marzo de ningún año (3.000 filas repartidas
entre 12 vendedores y ~12 meses, es esperable que algunas combinaciones den
cero). El asistente contestó eso mismo, sin inventar una cifra, y ofreció
preguntar por el año — que es la garantía central del asistente
funcionando como se esperaba, no un caso roto. Preguntando con el año
puesto ("marzo de 2026") contestó con el número real. De paso se reconfirmó
el trabajo del paso 21: con un filtro de vendedor activo en el Tablero, una
pregunta que no lo menciona igual contesta acotada a esa persona.

Fuera de esos dos casos, el checklist de `fase3-aceptacion.md` repasa los
7 pasos de la fase (16 a 22) con su evidencia ya documentada en los
commits anteriores, más algunas garantías transversales que valía la pena
dejar explícitas: el asistente nunca inventa un número (los dos casos de
arriba lo prueban con datos reales, no solo con el cliente falso), una
herramienta que falla no corta la conversación, y el visualizador no puede
ejecutar una operación de escritura ni por accidente.

Quedó anotada la deuda conocida de la fase, ninguna bloqueante: sin
memoria de conversación entre mensajes distintos (decisión de la fase,
paso 20), sin caché ni auditoría automática de tokens para el chat (a
diferencia de la inferencia), y un pedido nuevo de Sd que llegó en medio de
esta sesión — preguntas por voz en el cuadro del Tablero — que no estaba en
el plan aprobado de la fase 3 y queda para decidir su alcance como paso
aparte, probablemente ya en la fase 4 o como un paso corto antes.

345 tests de backend en verde (sin tests nuevos de este paso: es
verificación e integración, no funcionalidad); build y vitest del
frontend sin cambios. La organización descartable de la corrida de
referencia (`PruebaAceptacionFase3`) se borró al terminar; la demo no se
tocó en ningún momento de la fase.

**Fase 3 queda lista para que Sd la acepte.**

## 2026-09-12 — Dictado por voz en el cuadro de preguntas (v0.22.01)

Pedido de Sd que llegó en medio de la sesión de aceptación de la fase 3,
mientras se armaba `docs/fase3-aceptacion.md`: quería que el cuadro de
preguntas del Tablero también aceptara voz, y mencionó que ya lo había
hecho para un bot del panel de sindicato de otro proyecto suyo (Mi
Trabajo). No estaba en el plan aprobado de la fase 3; se avisó eso mismo y
se preguntó cómo seguir antes de tocar código. Sd contestó "agregá voz
ahora", así que se encaró en el momento como un agregado chico, sin la
ceremonia completa de lectura/dudas/plan que llevan las fases nuevas (es
una funcionalidad acotada sobre una pantalla que ya existía, no una fase).

La solución más simple y la única que no necesita nada nuevo del backend
ni un servicio pago: la Web Speech API del navegador
(`SpeechRecognition`, con el prefijo `webkit` para Chrome/Edge). Vive en
`asistente/vozWeb.ts`, un módulo chico que declara a mano los tipos que
hacen falta (TypeScript no trae tipos oficiales para esta API) y expone
`obtenerConstructorDeVoz()` (devuelve `null` si el navegador no la tiene:
en Firefox y Safari en iOS el botón de micrófono directamente no
aparece, en vez de mostrar un botón roto) y `transcriptoDe(evento)` para
juntar los resultados parciales en un solo texto.

`Chat.tsx` (pasos 20 y 21) ganó un botón de micrófono entre el campo de
texto y "Enviar"/"Preguntar", en las dos variantes (el cuadro del Tablero
y el panel flotante del constructor, porque las dos comparten el mismo
componente desde el paso 21). Al tocarlo arranca a escuchar en `es-AR`
con `interimResults` (el texto va apareciendo mientras la persona habla,
no hay que esperar a que termine de hablar para ver algo) y llena el
campo; el botón cambia de color y parpadea mientras escucha. Importante:
**no envía el mensaje solo por dictarlo** — la persona ve el texto
transcripto en el campo, lo puede corregir si escuchó mal algo, y lo
manda a mano como si lo hubiera tipeado. Evita que un error de
reconocimiento de voz mande una pregunta rota al asistente sin que nadie
lo revise.

Verificado en el navegador embebido de la sesión (que sí expone la API):
el botón aparece correctamente en las dos variantes de `Chat`, y al
tocarlo dispara de verdad el pedido de permiso de micrófono del navegador
— el entorno de pruebas lo bloquea por política de sandbox (no hay
micrófono real disponible ahí), pero eso mismo confirma que el código
llega hasta el punto correcto; cuando el permiso se niega, el botón
vuelve solo a su estado normal sin romper nada (`onerror`/`onend`
manejados). Queda pendiente una prueba con una persona hablando de
verdad frente a un micrófono real, que necesita un navegador de
escritorio normal en vez del embebido de esta sesión.

Build de Vite y los 7 tests de vitest sin cambios (frontend puro, sin
tests nuevos — se verifica en el navegador como el resto del frontend
desde el paso 6); la suite de backend no se tocó (no hay cambios de
backend en este agregado).

## 2026-09-12 — Dictado por voz: prueba de punta a punta y tests (v0.22.02)

Sd pidió probar el dictado por voz y avisarle dónde probarlo él. Como
Claude Code no tiene micrófono ni puede producir sonido, lo primero fue
decir eso con todas las letras: no se puede verificar el reconocimiento
de voz en sí (el motor entendiendo audio real) sin una persona hablando.
Lo que sí se podía hacer, y se hizo, fue probar todo lo demás.

Se agregaron 3 tests de vitest para `transcriptoDe` (junta los resultados
parciales y finales del reconocimiento en un solo texto), la única parte
de `vozWeb.ts` que es una función pura y se puede probar sin un navegador
de verdad — `obtenerConstructorDeVoz` lee `window`, que no existe en el
entorno Node de vitest (ni acá ni en `formato.test.ts`, el único archivo
de tests de frontend que había hasta ahora), así que esa función se dejó
sin test automático y se verifica a mano en el navegador.

Para la prueba de punta a punta sin un micrófono real, se interceptó
`start()` del motor de reconocimiento en el navegador embebido de la
sesión (mismo mecanismo real, `SpeechRecognition.prototype.start`
reemplazado para que dispare `onresult` con una transcripción fija en vez
de escuchar audio) — un truco de prueba, no un cambio en el código de la
app. Con eso: tocar el botón de micrófono llenó el campo con "cuánto
vendió Pérez en marzo" como si se hubiera dictado de verdad, y al enviarla
el asistente contestó "Pérez vendió $258.409,96 en marzo de 2026" — el
mismo número exacto de la corrida de referencia del paso 22, confirmando
que el texto dictado llega al chat exactamente igual que si se hubiera
tipeado. Eso prueba todo el camino propio del código (el botón, el estado
de React, el pedido al asistente, la respuesta) — lo único que quedó sin
probar es la parte que no depende del código de UBoard: si el motor de
reconocimiento del navegador entiende bien lo que dice una persona.

`docs/fase3-aceptacion.md` se actualizó con esta segunda vuelta de
pruebas. 10 tests de vitest en total (345 de backend sin cambios, no se
tocó nada del backend).

## 2026-09-12 — Fase 4, paso A: click-to-filter y el asistente aplica filtros (v0.23.01)

Sd pidió tres cosas de una: (1) que el chat pueda crear gráficos y filtros
con condiciones que hoy no existen (ej. "torta de ventas en efectivo por
vendedor" — una métrica filtrada, algo que ninguna fase anterior planeó),
(2) que el cuadro de preguntas pueda "aplicar filtro de ventas en
efectivo", y (3) que clickear un gráfico actúe como selector y filtre todo
el tablero, "como Qlik" — la misma funcionalidad que quedó anotada como
fuera de alcance para la fase 4 desde el primer día del proyecto
("filtrado asociativo"). Sd agregó que ya había hecho algo así para el
panel sindical del proyecto Mi Trabajo y pidió tomarlo de referencia.

Antes de tocar código se investigó ese panel (agente de exploración de
solo lectura sobre `C:\MiTrabajoC\validador-demo\validador-demo`). Hallazgo
importante: no es el modelo asociativo completo de Qlik. No existe el
tercer estado "posible" en gris (el propio documento de diseño de ese
proyecto lo dice explícito: solo hay seleccionado vs. el resto). El
mecanismo es un estado de filtros activos que vive en el frontend
(reflejado en la URL), con un `onClick` por gráfico que alterna (toggle)
un valor en ese estado, y cualquier cambio dispara de nuevo todos los
paneles. Esto es, casi literalmente, lo que UBoard ya tenía armado desde
la fase 1 para los chips de filtro (`FiltrosActivos` en la URL,
`filtrosUrl.ts`, cada panel refetch al cambiar) — así que la parte de
"click en un gráfico" resultó mucho más chica de lo que parecía al
principio: no hace falta tocar el compilador ni el motor de consultas en
absoluto, alcanza con conectar el click de ECharts al mismo mecanismo que
ya usaban los chips.

Con eso, se propuso partir el pedido en dos pasos: el paso A (click en un
gráfico + el asistente aplica un filtro que ya existe, mismo mecanismo
para las dos cosas) ahora; las métricas con un filtro propio (pedido 1)
para después, porque esa sí necesita una pieza de modelado nueva
(parecida a las fórmulas del paso 18) — no se puede resolver reusando lo
que ya hay. Sd aprobó "vamos por el A, luego con el resto".

`compartido/graficos/useGrafico.ts` ganó un parámetro `onClick` opcional:
se engancha al evento nativo `click` de la instancia de ECharts y devuelve
el `dataIndex` (la posición del punto clickeado en el arreglo de datos),
uniforme entre barras, torta y línea. `visualizador/Grafico.tsx` calcula
si el `campo` de algún filtro del spec (de tipo `lista` únicamente — un
click no alcanza para armar un rango de fecha, así que los gráficos de
línea, con dimensión de fecha, quedan afuera sin necesidad de un chequeo
aparte) coincide con la `dimension` del gráfico; si coincide, el gráfico
queda clickeable (cursor de mano, más una pista de texto "Clickeá para
filtrar por..."), y clickear un punto arma `{...filtrosActivos, [id]:
yaEsElUnico ? [] : [valor]}` con el mismo `onCambiar` que usan los chips
de `Filtros.tsx`.

Detalle de comportamiento que se aceptó a propósito, igual que en Mi
Trabajo: el gráfico clickeado también se re-filtra a sí mismo (clickear
"Ana Martínez" en "Top vendedores" hace que ese mismo gráfico, filtrado,
muestre una sola barra). Es la consecuencia esperable de no tener el
estado "posible" de Qlik — evitarlo pediría la complejidad que
deliberadamente se dejó afuera.

Del lado del asistente, `app/asistente/herramientas.py` ganó
`aplicar_filtro`: a diferencia de todas las demás herramientas de
escritura, está disponible para el VISUALIZADOR también (aplicar un
filtro no es una operación de modelo o dashboard, es puro estado de
pantalla) y no toca la base ni crea una versión — solo valida el filtro y
el valor contra el spec actual, reusando exactamente
`dashboard.filtros.a_filtros_de_consulta` (la misma función que ya
resolvía `GET /dashboard?filtros=`). El resultado validado (`entrada`,
`{filtro, valor}`) viaja de vuelta en la acción; para que el frontend lo
vea, `AccionSalida` (API) y `AccionAsistente` (frontend) ganaron el campo
`entrada`, que hasta ahora se guardaba pero no se exponía. `Chat.tsx`
reconoce la herramienta `aplicar_filtro` en la respuesta y llama a un
nuevo prop `onAplicarFiltro`, que en el Tablero está conectado al mismo
`cambiarFiltros` que usan los chips y el click en un gráfico — un solo
mecanismo, tres formas de dispararlo (chip, click, chat). Se actualizó el
prompt de sistema para que Claude sepa cuándo usar `aplicar_filtro` en vez
de tratar de contestar la pregunta con `consultar`.

Probado en Docker con una organización descartable: clickear la barra de
"Ana Martínez" en "Top vendedores" filtró todo el tablero (el KPI de total
de ventas coincidió exacto con el número ya verificado en la aceptación de
la fase 3, $3.757.825); clickear de nuevo sacó el filtro (verificado
disparando el click por JavaScript directo sobre el canvas, porque el
panel de pruebas de esta sesión tiene un desajuste de coordenadas conocido
entre la captura de pantalla y los píxeles reales — no fue un bug del
código). "Aplicá filtro de ventas en efectivo" en el cuadro de preguntas
activó el chip "Medio de pago: Efectivo" sin crear ninguna versión nueva.

4 tests nuevos en el backend (2 de forma del catálogo actualizados para el
tool nuevo, 3 de ejecución real de `aplicar_filtro`, 1 de punta a punta en
la API): 349 tests en total. Sin tests nuevos de frontend (se verifica en
el navegador, como el resto del frontend desde el paso 6); build y vitest
sin cambios.

Quedan pendientes, sin planificar en detalle todavía: el estado
"posible/excluido" en gris del modelo asociativo completo de Qlik, las
métricas con un filtro propio (pedido 1 de Sd), y un diagrama visual del
modelo tipo DER (pedido nuevo de Sd el mismo día, a evaluar aparte).

## 2026-09-12 — Diagrama del modelo, tipo DER (v0.24.01)

El mismo día del pedido de "actuar como Qlik", Sd pidió además evaluar un
diagrama visual del modelo — entidades y relaciones, "que se vea
profesional, agradable y elaborado", con la sugerencia de usar skills si
hacía falta. Se consultó el skill `frontend-design` del repo antes de
tocar código: su guía apunta a diseñar identidades visuales nuevas desde
cero, y UBoard ya tiene la suya, fijada desde el paso 7 ("informe
editorial": Newsreader serif, Source Sans 3, paleta de `tokens.css`). La
decisión fue no inventar una identidad nueva para esta pantalla, sino
tomar ese mismo lenguaje visual y ponerle un elemento propio y bien
resuelto: la notación "pata de gallo" (crow's foot) de un diagrama
entidad-relación de verdad, en vez de flechas genéricas — es la pieza que
hace que un diagrama de cajas y líneas se sienta como un DER profesional
y no como un dibujo improvisado.

Todo el trabajo quedó del lado del frontend, sin tocar el backend en
absoluto: el modelo semántico completo ya se puede pedir por `GET
/modelo` desde la fase 1, no hacía falta un endpoint nuevo.

`constructor/diagramaLayout.ts` es una función pura, `calcularLayout
(modelo)`, que arma las posiciones de cada entidad y cada conector. La
pieza que evitó tener que sumar una librería de layout de grafos (dagre,
elkjs, lo que fuera) es una garantía que el modelo ya tenía desde el
paso 4: la validación exige que el grafo de relaciones efectivas nunca
tenga ciclos (`MOD-REL-CICLO`), así que siempre es un bosque. Con eso
alcanza un BFS por capas desde las entidades de "hechos" (el centro
natural de un esquema en estrella) para conseguir un layout jerárquico
limpio, apilando una componente conexa debajo de la otra cuando hay más
de una. Cada conector se calcula desde la fila exacta del campo FK hasta
la fila exacta del campo PK, no solo entidad-a-entidad, para que la línea
apunte al campo correcto adentro de la caja.

`constructor/Diagrama.tsx` dibuja el resultado en SVG a mano: cada
entidad es una caja con cabecera (violeta suave si es "hechos", gris si
es "dimensión", con una sombra sutil), la clave primaria marcada con un
punto, el tipo semántico de cada campo como caption chica a la derecha, y
los campos `propuesta` o `rechazada` atenuados o tachados — la misma
lógica de "no ocultar el estado real" que ya usa el semáforo del wizard,
pero sin agregarle todos sus íconos, para no saturar el diagrama. La
notación "pata de gallo" se arma con paths de SVG a mano: tres líneas que
convergen en el borde de la caja para el lado "muchos", dos marcas
perpendiculares para el lado "uno" — calculado a partir de `cardinalidad`
(`n:1`, `1:n`, `1:1`), el mismo campo que ya usa el compilador para saber
qué lado tiene que ser la clave primaria. Todo el color sale de las
variables de `tokens.css` de siempre, así que el diagrama responde al
modo oscuro sin ningún código extra — se verificó explícitamente
alternando el tema en el navegador.

Se agregó una pestaña "Diagrama" en Modelo, junto a Revisión, Avanzado y
Dashboard, reusando la misma query (`["modelo", workspaceId]`) que ya
usa Revisión — abrir el diagrama no dispara un pedido nuevo si el modelo
ya está en caché.

7 tests de vitest nuevos para `diagramaLayout.ts` (la parte pura y con
valor real de probar: capas por BFS, qué lado de cada conector es
"muchos"/"uno", qué campos quedan marcados como clave, que una entidad
sin relaciones no rompe el layout) — 17 tests de frontend en total. El
dibujo en sí (`Diagrama.tsx`) no tiene tests, es una traducción directa de
coordenadas a SVG, sin lógica propia; se verificó a mano en el navegador,
en claro y oscuro, contra el modelo real de una organización de prueba
(borrada al terminar). Sin cambios de backend, sin tests nuevos ahí.

## 2026-09-12 — Métricas con un filtro propio (v0.25.01)

El mismo pedido de "quiero poder crear filtros con los asistentes y crear
gráficos también, ej. 'quiero agregar un gráfico de torta ventas en
efectivo por vendedor', hoy no se puede" traía adentro dos problemas
distintos: filtrar y graficar por chat (paso A, ya resuelto) y una pieza
que faltaba en el modelo mismo — "ventas en efectivo" no existía como
métrica, porque el medio de pago vive en `medios_pago`, tres saltos de
`ventas`, y ninguna métrica del modelo se sabía filtrar así.

Antes de tocar código se le preguntó a Sd por dos decisiones reales con
`AskUserQuestion`. La primera, cuánto alcance darle al filtro de una
métrica: la opción chica solo soporta caminos "seguros" (JOIN, como una
dimensión más); la potente soporta también caminos del lado "muchos"
(EXISTS). Sd eligió la potente — es justo el caso de "ventas en
efectivo", porque `ventas` → `pagos` es 1:n, un camino inseguro. La
segunda, si el wizard necesitaba un control para armar el filtro a mano o
alcanzaba con que lo arme el chat: eligió las dos cosas juntas, mismo
criterio que ya se usó en el paso 18 (fórmulas). Una tercera pregunta, ya
sobre el otro pendiente de la sesión (el estado gris tipo Qlik), quedó
resuelta para más adelante: empezar por la versión chica (opciones de
filtro), no por la versión completa (gráficos en gris).

**El modelo.** `ExpresionAgregacion` gana `filtros: list[FiltroConsulta]`
— una condición que viaja pegada a la métrica y se aplica siempre que se
la usa, en cualquier consulta, distinto de un filtro del dashboard (que
es de la persona que mira, no de la métrica). Para poder embeber un
`FiltroConsulta` adentro de una métrica del modelo hubo que resolver un
problema de dependencias: `FiltroConsulta` y `Operador` vivían en
`consultas/esquema.py`, que ya importa cosas de `modelo/esquema.py` — si
`modelo/esquema.py` los hubiera importado de vuelta, ciclo. Se mudaron
los dos a `modelo/esquema.py` (tiene más sentido ahí de todos modos: un
filtro de métrica es parte del modelo, no de una consulta puntual) y
`consultas/esquema.py` quedó reexportándolos, así que ningún llamador
externo — y son bastantes — tuvo que cambiar una línea. Se verificó a
mano que no había ciclo (ejecutando el import directo) y con la suite
completa en verde.

**El compilador.** Es la pieza más delicada. `_columna_agregacion` mira,
para cada filtro propio de una métrica, el camino desde la entidad de la
métrica hasta la entidad del filtro — el mismo `_camino` que ya usa el
compilador desde el paso 5 para dimensiones y filtros de consulta. Si el
camino es seguro, lo resuelve con JOIN, igual que una dimensión más. Si
en algún punto el camino pasa por el lado "muchos", resuelve esa parte
con EXISTS — reusando el semi-join que ya existía para "ventas que
tienen algún pago en efectivo" (paso 5), no una pieza nueva. La columna
agregada queda envuelta en `CASE WHEN <condición> THEN columna ELSE NULL
END`: como las seis agregaciones (`suma`, `conteo`, `conteo_distinto`,
`promedio`, `minimo`, `maximo`) ignoran NULL, el mismo truco sirve para
todas sin un caso especial por agregación.

Se encontró y resolvió una sutileza de posiciones antes de correr el
primer test: los parámetros `?` del filtro de la métrica están en el
SELECT, los del filtro del dashboard están en el WHERE, y DuckDB liga los
parámetros posicionalmente según el orden en que aparecen en el SQL
final — así que había que juntar primero los parámetros de las columnas
agregadas y recién después los del WHERE, no al revés. Los cuatro tests
nuevos de compilador lo confirmaron a la primera.

**El wizard y el chat.** El wizard (`constructor/Revision.tsx`, sección
Métricas) suma un checkbox "Con filtro" a "Crear una métrica": tildado,
aparecen los tres controles (campo — cualquier campo del modelo, no solo
los numéricos que ya se ofrecían para la métrica en sí —, operador y
valor). La tabla de métricas ahora muestra el filtro en la columna
Expresión (`suma(ventas.importe) donde medios_pago.nombre = Efectivo`).
El chat no necesitó una sola línea de cambio para poder crear métricas
filtradas: el esquema de la herramienta `crear_metrica` que ve Claude
sale en vivo de `ExpresionAgregacion.model_json_schema()`, así que en
cuanto el modelo Pydantic tuvo el campo `filtros`, Claude ya lo podía
usar — se confirmó pidiéndole en la práctica el ejemplo textual de Sd.

**Verificación de punta a punta.** Con una organización descartable
(datos de prueba de siempre, cargados vía `cargar_prueba.py`) se probaron
los dos caminos por separado: desde el wizard se creó "Ventas en
efectivo" (`suma(ventas.importe)` filtrado por `medios_pago.nombre =
Efectivo`, el camino inseguro que resuelve con EXISTS) y quedó confirmada
al toque por ser de origen `usuario`; en el mismo chat, sin decirle nada
de la métrica recién creada, se le pidió literalmente "quiero agregar un
grafico de torta ventas en efectivo por vendedor" — contestó que lo
había agregado, usó la métrica `ventas_efectivo` con la dimensión
`vendedores.nombre`, y el gráfico apareció en el tablero con números
correctos (se verificaron contra la API del gráfico: la suma en efectivo
por cada vendedor, con el grupo de vendedor nulo incluido por el LEFT
JOIN, como corresponde). Organización de prueba borrada por SQL crudo al
terminar, según la regla de siempre (el cascade del ORM choca con un
check constraint).

8 tests nuevos de compilador + 2 de validación de modelo + 1 de edición
(la creación de una métrica filtrada por la operación granular
`crear_metrica`) — 355 tests de backend en total. Frontend: build y
`vitest` en verde, sin tests nuevos de componente (mismo criterio que el
resto del wizard desde el paso 13, se verifica a mano en el navegador).

## 2026-09-13 — Estado gris de Qlik, versión chica: opciones de filtro (v0.26.01)

Este era el segundo de los dos pendientes que quedaron del pedido "actuá
como Qlik" ("1) filtros y gráficos por chat, 2) aplicar filtro por chat,
3) clickear un gráfico como selector"). El punto 3 tiene dos capas: el
paso A (ya resuelto) hizo que clickear un gráfico o pedirle al chat
aplicara un filtro; esta era la otra capa, el estado "gris" — en Qlik,
cuando elegís un valor en un campo, los valores de OTROS campos que ya no
tienen datos con esa elección se ven distintos (grisados), sin
desaparecer. Antes de tocar nada se le preguntó a Sd por `AskUserQuestion`
cuánto alcance darle de entrada: la versión completa (gráficos también en
gris) o la chica (solo las opciones de los filtros de lista). Eligió la
chica — es la pieza más chica y más útil primero, y la de los gráficos
queda para más adelante.

El diseño salió de mirar lo que ya existía: `GET
/dashboard/filtros/{id}/opciones` (paso 6) siempre devolvió TODOS los
valores del campo, sin mirar los demás filtros — "sin asociativo hasta la
fase 4" decía el propio comentario del código. La pieza que faltaba era
calcular, además del universo completo, qué subconjunto de esos valores
sigue dando resultado si se aplican los OTROS filtros que están activos
en el Tablero en ese momento (nunca el propio: elegir "Centro" en
Sucursal no tiene por qué grisarse a si mismo).

Del lado del backend fue chico porque toda la maquinaria ya existía:
`ContextoDashboard` (que ya arma `self.filtros` a partir del `?filtros=`
crudo) ganó `filtros_sin(filtro_id)`, que repite la misma conversión pero
sacando esa clave del diccionario antes. `consulta_opciones_lista`
(`dashboard/paneles.py`) ganó un parámetro opcional de filtros que pasa
tal cual a la `ConsultaSemantica` de siempre — nada nuevo en el
compilador, es la misma consulta de "valores distintos de un campo" que
ya se usaba, solo que ahora puede llevar condiciones. El endpoint hace
como mucho dos consultas: la de siempre (universo, sin filtros) y, solo
si hay otros filtros activos, una segunda con esos otros filtros
aplicados; si no hay otros activos, ni se corre la segunda — `disponibles`
queda en `None`, que el frontend interpreta como "nada que grisar".

Se probó con un caso elegido a propósito por ser 100% determinístico y no
depender de que los datos sintéticos tengan tal o cual distribución al
azar: cada vendedor de los datos de prueba pertenece a una sola sucursal
(4 en Centro, 4 en Norte, 4 en Oeste). Filtrar por Sucursal = "Centro" y
pedir las opciones de Vendedor tiene que dejar disponibles exactamente
esos 4 nombres, nunca más ni menos — y al revés, filtrar por un vendedor
de Centro tiene que dejar disponible solo "Centro" en Sucursal. El test
nuevo verifica las dos direcciones más el caso de "un filtro no se
restringe a si mismo" (con Sucursal ya en "Centro", pedir las opciones de
Sucursal no tiene que grisar nada, porque los "otros filtros" para ese
pedido están vacíos).

Del lado del frontend, `visualizador/Filtros.tsx` ya recibía `filtros`
(todos los activos) como prop desde el Tablero, así que alcanzó con
pasarlo al `useOpciones` del control de lista (el de rango de fecha no
cambió, a propósito: el alcance elegido fue solo las opciones de lista) y
sumarlo a la `queryKey` para que el popover se recalcule solo cuando
cambia OTRO filtro. Las opciones que `disponibles` no trae se pintan con
el tono `--mudo` que ya usa el resto de la UI para texto secundario, más
un "(sin datos)" alineado a la derecha — sin sacarlas de la lista ni
impedir seleccionarlas, es una pista visual nomás, no una restricción
dura (elegir igual una opción grisada es válido, el resultado
simplemente va a dar cero filas, y eso ya se ve reflejado en los KPIs).

Se probó de punta a punta en Docker con una organización descartable:
sin ningún filtro activo, las tres sucursales aparecen normales; al
activar Sucursal = "Centro", el popover de Vendedor muestra los 4 nombres
de Centro sin marca y los otros 8 con "(sin datos)" en gris — exactamente
la lista que predijo el test. Se ajustó la posición del texto (probado
primero pegado al nombre, se veía apretado y cortaba línea en nombres
largos; se lo pasó a alineado a la derecha con `margin-left: auto` y
`white-space: nowrap`) después de verlo en el navegador.

1 test nuevo de API (356 en total); sin tests nuevos de frontend, mismo
criterio que el resto de esta pantalla desde el paso 7 (se verifica a
mano en el navegador). Organización de prueba borrada por SQL crudo al
terminar.

## 2026-09-13 — Fase 4: integración y aceptación (v0.26.02)

Con las cuatro piezas de la fase hechas (paso A, diagrama del modelo,
métricas con un filtro propio, estado gris de las opciones), tocaba
cerrar la fase con el mismo tipo de checklist que las fases 1, 2 y 3
—aunque, a diferencia de esas, la fase 4 no arrancó con un documento de
lectura/dudas/plan (fue ad-hoc, a pedido de Sd en medio de otra sesión),
así que el "criterio de aceptación" no salía de un §9 escrito de
antemano. Se armó revisando qué decía la especificación original sobre
esto: desde el §1, UBoard siempre iba a proponer un "dashboard
asociativo", y el §6 (paso del visualizador) ya describía en detalle el
mecanismo de verde/gris propagado por el grafo de relaciones — esta fase
entrega una primera porción real de eso, no la versión completa que
imaginaba la especificación (que hablaba incluso de un módulo
`asociativo/` propio con cache por combinación de filtros).

En vez de repetir las verificaciones aisladas que ya se habían hecho paso
por paso (cada una documentada en su propia entrada de este archivo), la
aceptación se probó con una corrida COMBINADA: una sola organización
descartable, una sola sesión de navegador, tocando las cuatro piezas
seguidas para confirmar que siguen andando juntas y no solo por
separado. Diagrama del modelo (las 5 entidades del dataset de prueba,
notación pata de gallo); click en la barra de "Diego López" en "Top
vendedores" (filtró el dashboard entero de 3.000 a 261 ventas); con ese
filtro activo, el popover de "Sucursal" mostró "Oeste" limpio y
"Centro"/"Norte" grisados — Diego López es justamente de Oeste en los
datos de prueba, así que el gris cayó exactamente donde tenía que caer;
y por último, sacando el filtro de vendedor, pedirle al chat "aplicá el
filtro de medio de pago efectivo" lo aplicó bien (`aplicar_filtro`, sin
crear una versión nueva).

Un detalle técnico de esta sesión, no del código: al reproducir el
click-to-filter para la corrida de referencia, el primer intento con
varias coordenadas no encontró la barra — resultó ser que las
coordenadas usadas (con `resize_window` a un tamaño grande) caían sobre
el área de las ETIQUETAS de vendedor del eje, no sobre las barras mismas
(la etiqueta no dispara el evento de click de una serie de ECharts, solo
la barra sí). Se resolvió tomando una captura real de la pantalla,
midiendo a ojo dónde caía la barra dentro del canvas, y recién ahí
calculando el punto para el evento sintético — la técnica de siempre
(`MouseEvent` disparado a mano vía `getBoundingClientRect`, del paso A)
seguía siendo válida, solo hacía falta apuntar al lugar correcto.

Se escribió [`docs/fase4-aceptacion.md`](fase4-aceptacion.md) con el
detalle completo, una tabla de 10 criterios (todos ✅) y los pendientes
conocidos que quedan fuera de esta fase a propósito (el gris completo de
Qlik en los gráficos, la propagación por el grafo con cache que imaginaba
la especificación). De paso quedó anotado que la fase 3 tampoco tiene
todavía un "acepto" explícito de Sd — el trabajo siguió derecho hacia la
fase 4 sin esa confirmación formal — por si quiere cerrar las dos juntas.

Sin cambios de código en este paso (solo el documento de aceptación y la
verificación). 356 tests de backend, build y 17 de vitest sin cambios.
Organización de prueba (`PruebaAceptacionFase4`) borrada por SQL crudo al
terminar; la demo no se tocó.

## 2026-09-13 — Fase 3 y fase 4 aceptadas por Sd

Sd contestó "acepto" a la propuesta de cerrar las dos fases juntas: la
fase 3 (asistente), que había quedado documentada como "lista para
aceptar" desde el paso 22 pero sin una confirmación explícita porque el
trabajo siguió derecho hacia la fase 4 a pedido suyo; y la fase 4
(interacción y filtrado asociativo), con el checklist recién armado en
`docs/fase4-aceptacion.md`. No hay todavía un plan de una fase 5 para
presentar — la fase 4 sigue abierta en los hechos (quedan pendientes
conocidos, como el estado gris completo en los gráficos), así que por
ahora esto es un cierre formal de lo hecho hasta acá, no un arranque de
etapa nueva.

## 2026-09-13 — Memoria corta del chat y UX de voz (v0.27.01)

Con la fase 4 recién aceptada, Sd mandó un ejemplo real de un diálogo que
"no puede pasar": le pidió algo al asistente, este propuso un gráfico
("¿Te sirve así?"), Sd contestó "sí sirve", y el asistente respondió "¿A
qué te referís con 'sí sirve'? No tengo el pedido anterior a la vista".
No era un caso hipotético — era exactamente la limitación que ya estaba
anotada como deuda conocida desde `docs/fase3-aceptacion.md` ("sin
memoria de conversación entre mensajes... un pedido muy elíptico que
dependa de lo dicho en el mensaje anterior puede no tener con qué
reconstruirse") y que ese mismo documento proponía como arreglo futuro:
"se puede agregar mandando el historial de turnos de ida y vuelta entre
frontend y backend sin persistir nada en la base". Llegado el caso real,
tocaba resolverlo.

La decisión de diseño (fase 3, duda 3) de no persistir la conversación en
la base **no cambió** — sigue sin haber una tabla de mensajes. Lo que se
agregó es memoria de UNA conversación, viajando en cada pedido: el
frontend ya guardaba todo el historial de la pantalla en su estado de
React (se pierde al refrescar, siempre fue así); ahora ese mismo
historial se manda como `historial` en el `POST .../asistente/mensajes`,
y `motor.conversar` lo antepone a los mensajes que arma para Claude como
turnos reales `user`/`assistant` (no como texto dentro del "Contexto
actual" JSON, que es donde va el modelo y el dashboard) — así Claude ve
literalmente lo que dijo antes, en su propio formato de conversación.
Recortado a los últimos 6 turnos (constante `MAX_TURNOS_HISTORIAL`, en
las dos puntas: el frontend igual manda su historial completo de la
sesión, pero el motor solo usa los últimos 6 al armar el pedido) para que
una conversación larga no infle el costo de cada pregunta sin límite. Se
sumó además una regla explícita al prompt de sistema pidiéndole a Claude
que, ante una confirmación corta a algo que él mismo propuso, actúe en
vez de volver a preguntar — refuerzo, no reemplazo del historial real.

Se reprodujo el bug tal cual en Docker antes de tocar código (pedirle
"agregá un gráfico de ventas por medio de pago y por vendedor", que fuerza
una aclaración porque cruza dos dimensiones, y contestar solo "sí sirve")
y se confirmó el arreglo después: la misma secuencia ahora hace que el
asistente aplique lo que había propuesto, sin preguntar de nuevo.

De paso, cuatro pedidos de UX para el dictado por voz, todos sobre
`asistente/Chat.tsx` y `vozWeb.ts`:

1. **Auto-envío a los 4 segundos de silencio.** El reconocimiento pasó de
   `continuous: false` (dejaba que el navegador decidiera solo cuándo
   cortar, con su propia detección de pausas, poco controlable) a
   `continuous: true`, y ahora es el propio componente el que mide el
   silencio: cada resultado nuevo de voz reinicia un timer a 4000 ms: si
   pasan los 4 segundos sin un resultado nuevo, se corta el dictado y se
   manda la pregunta sola.
2. **Botón "Stop".** El mismo botón de micrófono, mientras está
   escuchando, pasa a mostrar `⏹` y su función cambia: en vez de solo
   cortar el dictado (dejando lo transcripto en el campo, como antes),
   corta Y BORRA el texto. La lógica: si la persona lo toca a mano en vez
   de dejar que el silencio lo mande solo, es porque algo salió mal en la
   transcripción y quiere descartarlo, no solo pausar.
3. **Cancelar un pedido en vuelo** ("si se puede, también después de
   enviar"). Mientras se espera la respuesta del asistente, el botón de
   enviar se reemplaza por "Cancelar", que aborta el `fetch` con un
   `AbortController` (el cliente HTTP `pedir()` ya soportaba `signal` sin
   cambios, es una opción estándar de `fetch`). Un aborto deja un mensaje
   neutro "Cancelado." en el chat en vez del texto crudo de `AbortError`.
   Aclaración importante que quedó en `CLAUDE.md`: esto es "mejor
   esfuerzo" del lado del navegador nomás — no hay forma de garantizar
   que el pedido se corte también del lado del servidor sin agregar
   chequeos de desconexión en cada vuelta del loop de herramientas, cosa
   que no se hizo (no la pidió Sd, que dijo "si se puede").
4. **Botón de cerrar (`✕`)** arriba a la derecha de la cabecera del panel
   flotante del constructor, además del botón flotante de siempre (que
   ahora dice siempre "💬 Asistente" en vez de alternar a "✕ Cerrar",
   redundante con el nuevo botón).

Y un quinto pedido, de layout, sin relación con la voz: el cuadro
"Preguntale a tus datos" del Tablero es un 30% más ancho en pantallas de
escritorio (`@media (min-width: 721px)`, el mismo umbral que ya usaban
`Filtros` y `Marco` para distinguir mobile de desktop) — en mobile sigue
igual que antes.

Verificación en Docker: para el auto-envío y el botón Stop, se usó la
misma técnica del paso de dictado original (interceptar `start()` y
`stop()` del motor de reconocimiento del navegador, sin tocar código de
la app) pero esta vez capturando la instancia real para poder disparar
resultados de voz simulados con timing controlado dentro de un solo
script: confirmado que a los 2 segundos de un resultado nuevo todavía no
se había enviado nada, y que pasados los 4 segundos sin un resultado
nuevo se envió solo; por separado, que tocar "Stop" corta el dictado,
vacía el campo y que efectivamente no se manda nada aunque pase el mismo
tiempo. Para "Cancelar", se mandó un pedido real y se lo abortó a los 30
ms: apareció "Cancelado." y no se aplicó ninguna acción. Botón de cerrar
y ancho del cuadro verificados por inspección del DOM y estilos
computados.

5 tests nuevos de backend (`test_motor.py`, `test_asistente_api.py`): que
el historial llega como turnos `user`/`assistant` reales, que se recorta
a los últimos `MAX_TURNOS_HISTORIAL`, que sin historial el comportamiento
es exactamente el de antes, y que un turno con un rol inválido es
`422` (361 tests en total). Sin tests nuevos de frontend — mismo criterio
que el resto de esta pantalla desde el paso 20, se verifica a mano en el
navegador. Organización de prueba (`PruebaMemoriaChat`) borrada al
terminar.

## 2026-09-13 — Orden personal por arrastre (v0.28.01)

Sd trajo una observación de diseño, no un bug: "en el dashboard todos los
datos y gráficos tienen un orden establecido bastante caótico. Sería
bueno que cada uno de ellos pudiera ser movido y reubicado en pantalla
conformando una especie de template del usuario". Antes de escribir una
línea de código se acotó el alcance con dos preguntas cortas, en prosa
(no hacía falta `AskUserQuestion`, eran decisiones chicas):

1. **¿Arrastre libre en una grilla, o reordenar dentro de cada sección?**
   Se recomendó lo segundo: la dirección visual del paso 7 ("informe
   editorial") tiene una jerarquía de lectura deliberada — cifra
   protagonista grande, gráficos en orden, planilla de detalle abajo — y
   mezclar KPIs con gráficos en una grilla libre la habría roto. Sd
   confirmó.
2. **¿El orden viaja en el spec versionado (compartido, sincronizado
   entre dispositivos) o queda como preferencia personal en el navegador
   (simple, sin sincronizar)?** Se recomendó la preferencia personal: el
   spec de fase 1 es la estructura del dashboard, compartida por toda la
   organización, con su propio historial de versiones — mezclar ahí "cómo
   prefiero verlo yo" con "cómo está armado el dashboard" habría
   ensuciado ese historial con un ruido nuevo por cada arrastre. Sd contestó
   "vamos por la simple".

Con las dos decisiones tomadas, **no hizo falta tocar el backend en
absoluto**: todo el trabajo quedó del lado del frontend.

`compartido/ordenPersonal.ts` tiene el hook `useOrdenPersonal(tipo,
workspaceId, items, idDe)`: lee y guarda el orden en `localStorage`, con
una clave por tipo de bloque, workspace y usuario
(`uboard:orden:{tipo}:{workspaceId}:{usuarioId}`) para que dos personas
en la misma compu no se pisen el orden. La parte que vale la pena probar
de verdad —qué pasa si el spec cambió desde la última vez (un KPI nuevo,
un gráfico que ya no existe)— se separó en dos funciones puras,
`combinarOrden` (mezcla lo guardado con lo actual: los conocidos
mantienen su lugar relativo, los nuevos van al final, los que
desaparecieron se ignoran) y `moverEnOrden` (mueve un id justo antes de
otro), siguiendo el mismo patrón que ya se usó para `diagramaLayout.ts`
en la fase 4: la lógica pura separada del hook que toca el navegador, así
se puede probar con vitest sin simular React ni el DOM.

`compartido/arrastre.ts` tiene `useArrastreDeOrden(mover)`, que separa
las props de dos roles: el "agarradero" (el elemento chico que arranca el
arrastre, con `draggable` de verdad) y el "contenedor" (el elemento
grande que recibe el `drop`). La separación no es capricho: los gráficos
ya tienen su propio manejo de mouse adentro (el click-to-filter del paso
A, sobre el canvas de ECharts), así que hacer arrastrable la figura
ENTERA hubiera arriesgado interferir con esos clicks. La solución fue un
agarradero chico (`⠿`) en la cabecera del gráfico, al lado de "Ver
tabla", lejos del cuerpo donde vive el click-to-filter — el contenedor
que recibe el drop sigue siendo la figura completa, para que soltar en
cualquier parte de la tarjeta funcione. En los KPIs y en las pestañas del
explorador, que no tienen nada interactivo adentro, el mismo elemento
sirve de agarradero y de contenedor a la vez, sin necesidad de esa
separación.

`Kpis.tsx`: el orden se aplica a la lista COMPLETA antes de separar
protagonista y resto, así que arrastrar cualquier KPI chico al lugar de
la cifra grande lo promueve (y el que estaba ahí baja a la grilla).
`Tablero.tsx`: mismo patrón con `spec.graficos` antes de separar el
gráfico principal (ancho, arriba) de los secundarios (grilla de 2).
`Explorador.tsx`: el orden se aplica a las pestañas antes de pasarlas al
componente compartido `Pestanias.tsx`, que ahora acepta un prop opcional
`arrastre` — opcional a propósito, porque el mismo componente también
arma las pestañas FIJAS de Modelo (Revisión/Diagrama/Avanzado/Dashboard),
que no tienen que ser arrastrables; sin ese prop, `Pestanias` se comporta
exactamente igual que antes.

Un bug real, encontrado ANTES de cerrar el paso (no llegó a Sd): al
verificar en Docker, el Tablero explotaba con un error de React (#310) en
cuanto cargaba. La causa fue una violación clásica de las reglas de los
hooks: `useOrdenPersonal` y `useArrastreDeOrden` habían quedado
DESPUÉS de los `return` tempranos de `Tablero.tsx` (los de "cargando" y
"hubo un error"), así que en el render de éxito el componente llamaba más
hooks que en los renders de carga/error — React lo detecta y tira ese
error específico. Se solucionó subiendo las dos llamadas arriba de todo,
antes de cualquier `return`, usando `dashboard.data?.contenido.graficos
?? []` mientras el dashboard todavía no llegó (un array vacío no rompe
nada, simplemente no hay nada para reordenar todavía). Quedó anotada la
regla en `CLAUDE.md` para no repetirlo la próxima vez que se agregue un
hook a un componente con `return`s tempranos.

Verificado en Docker contra la demo real (sin alterarla — el orden vive
en `localStorage` del navegador, nunca toca la base de la organización):
arrastrar "Unidades vendidas" al lugar de la cifra protagonista la
promovió, bajando "Total ventas" a la grilla chica; arrastrar el gráfico
"Cobros por medio de pago" al lugar del gráfico principal lo agrandó;
arrastrar la pestaña "Pagos" al principio del explorador la reordenó; el
orden sobrevivió a un F5 (se lee de `localStorage` en el primer render);
y — la prueba más importante — el click-to-filter sobre una barra de
"Top vendedores" siguió aplicando el filtro exactamente igual que antes,
confirmando que el agarradero separado no interfiere con el canvas.

10 tests nuevos de vitest para `combinarOrden` y `moverEnOrden` (27 en
total: casos de mezcla con elementos nuevos/eliminados, mover hacia
adelante y hacia atrás, mover al propio lugar, origen o destino
inexistente). Sin tests de componente — se verifica arrastrando de
verdad en el navegador, mismo criterio que el resto de esta pantalla
desde el paso 7. Sin cambios de backend: la suite sigue en 361 tests,
sin cambios desde el paso anterior.

## 2026-09-13 — Arreglo del arrastre: insertar tambien "despues", icono visible (v0.28.02)

Sd probó la primera versión del orden por arrastre y avisó dos problemas
concretos: "ahora veo el ícono (muy poco visible) y la verdad es que el
movimiento no es libre solo puedo intercambiar la posición de un gráfico
con otro. Bastante inservible".

El segundo problema, revisado el código, resultó ser un límite real del
diseño, no una percepción equivocada de Sd: `moverEnOrden` solo sabía
insertar el elemento arrastrado JUSTO ANTES de donde se soltaba. Con
pocos elementos (4 o 5 KPIs, 6 gráficos), la única maniobra posible en la
práctica termina pareciéndose a un intercambio de a pares, porque nunca
se puede dejar algo genuinamente AL FINAL de la lista — soltarlo sobre el
último elemento lo deja justo antes de ese último, nunca después. Eso
explica el "bastante inservible": para reordenar de verdad hacía falta
justo la única operación que no estaba disponible.

La solución fue agregarle a `moverEnOrden` un tercer parámetro, `lado:
"antes" | "despues"`, y decidir cuál corresponde según en qué mitad del
elemento se suelta. La geometría quedó en una función pura nueva,
`ladoDeSoltar` (`compartido/arrastre.ts`, que ahora solo tiene esto — la
parte con estado se mudó a `ordenPersonal.ts`): en vez de mirar solo el
eje X o solo el eje Y (que hubiera necesitado saber si cada layout es una
fila, una columna o una grilla de 2), mira la diagonal del rectángulo:
si el puntero cae en la mitad de arriba-a-la-izquierda es "antes", si
cae en la de abajo-a-la-derecha es "después". Funciona razonablemente
para los tres layouts de esta pantalla (la fila de pestañas, la grilla
de 2 columnas de KPIs y gráficos, los bloques sueltos) sin necesitar una
configuración distinta para cada uno.

De paso se sumó algo que la primera versión tampoco tenía: vista previa
EN VIVO mientras se arrastra. Antes, arrastrar un elemento por encima de
varios otros no mostraba nada hasta soltar — un solo salto discreto al
final, que reforzaba la sensación de "intercambio" en vez de reordenar
de verdad. Ahora `useOrdenPersonal` mantiene un estado transitorio
(`vistaPrevia`) que se recalcula en cada `dragover` (recorriendo la
misma `moverEnOrden`, esta vez sobre el estado previo, no sobre el orden
persistido), así que los demás elementos se van corriendo para hacer
lugar a medida que uno arrastra — recién al soltar (`onDrop`) esa vista
previa se guarda de verdad en `localStorage`; si se suelta afuera de
cualquier elemento válido, `onDragEnd` la descarta sin persistir nada y
todo vuelve a como estaba.

El primer problema — el ícono "muy poco visible" — era el caracter
Unicode `⠿` (del bloque Braille), que en Source Sans 3 se renderiza como
un punto chico y débil, casi imperceptible con el color apagado
(`--mudo`) que se le había puesto. Se reemplazó por un componente propio,
`compartido/componentes/AgarraderoArrastre.tsx`: un SVG a mano de seis
círculos (el símbolo de "agarradero" más reconocible en el mundo del
software, el mismo patrón visual que usan Trello, Notion, etc.) adentro
de una pastilla con borde y fondo (`var(--superficie-2)`), así el tamaño
y el contraste no dependen de qué fuente tenga instalada quien lo mire.

Verificado en Docker reproduciendo el caso puntual: se armó una corrida
que arrastra un KPI y lo suelta pasado el último elemento de la lista —
en la primera versión esto era imposible (quedaba tercero de cuatro, no
cuarto); con el arreglo, queda efectivamente último. Se probó lo mismo
con un gráfico. También se verificó la vista previa en vivo, arrastrando
un elemento por encima de tres posiciones distintas antes de soltar y
confirmando que la lista se reacomodaba en cada paso intermedio, no solo
al final. El click-to-filter de los gráficos (paso A) siguió andando
exactamente igual, confirmando que el agarradero separado del contenedor
sigue sin interferir.

4 tests nuevos de vitest para `ladoDeSoltar` (las esquinas, el centro
exacto como caso límite a favor de "antes", y un rectángulo sin tamaño
que no debería pasar en la práctica pero tampoco rompe nada) y 2 casos
nuevos para `moverEnOrden` con `"despues"` (35 tests de frontend en
total). Sin cambios de backend: la suite sigue en 361 tests, sin cambios.
Organización descartable no hizo falta esta vez: se verificó contra la
demo real sin alterarla (el orden vive en `localStorage`, nunca toca la
base).

## 2026-09-13 — Espacio muerto debajo de los KPIs, y backlog de ventanas libres (v0.28.03)

Sd notó algo que venía de antes de esta sesión, no del arrastre: "debajo
de los KPI y a la izquierda de la pantalla queda un espacio de casi un
tercio del ancho total que no se puede poner nada". Aprovechó para
preguntar, de paso, qué tan costoso sería ir más lejos: "ventanas" que se
puedan mover libremente por toda la pantalla y redimensionar, como un
canvas de verdad (Grafana, Power BI en modo edición).

Antes de tocar código se conversó el alcance, en prosa, sin necesidad de
`AskUserQuestion` porque no había una decisión de arquitectura ambigua
sino una pregunta de costo honesta. La respuesta: son dos cosas de
tamaño muy distinto. El espacio muerto es un ajuste de CSS chico — la
grilla de 2 columnas (`minmax(280px,4fr) 8fr`) estira ambas columnas a
la misma altura, y como la de KPIs tiene menos contenido que la de
gráficos, sobra espacio abajo. Las ventanas libres y redimensionables son
un salto real: cambia el modelo de datos (de "un orden de ids" a
"posición x/y y tamaño por panel"), necesita manijas de resize,
lógica para que no se superpongan o para que fluyan al achicar la
ventana, y una decisión de qué pasa en el celular. Se le comentó a Sd que
probablemente convendría sumar una librería chica y madura
(`react-grid-layout` es la más usada) en vez de escribir todo eso a
mano — sería la primera dependencia de UI externa de todo el frontend,
que hasta ahora fue deliberadamente "cero librerías" (ni Tailwind, ni un
kit de componentes, ECharts directo sin wrapper). Sd preguntó además si
sacar el resize de mobile del alcance reducía mucho el trabajo: la
respuesta fue que no — ahorra construir manijas táctiles y la UX de
redimensionar con el dedo en una pantalla chica, pero el motor de
posicionamiento libre en sí (el modelo de datos, las colisiones, el
drag con resize en desktop) es el mismo trabajo esté o no mobile
involucrado, porque esa complejidad vive del lado de escritorio igual.

Con esos números sobre la mesa, Sd decidió: la versión chica ahora,
ventanas libres y redimensionables **al backlog, sin fecha**.

La versión chica: separar, en `Tablero.tsx`, el gráfico principal (el
que acompaña a los KPIs arriba) de los gráficos secundarios. Antes, los
tres vivían adentro de la misma `<section>` confinada a la columna
angosta de 8/12 al lado de los KPIs — ahí es donde se generaba el hueco,
porque esa columna entera (incluidos los secundarios) terminaba tan alta
como hiciera falta para acomodarlos a todos, mientras la columna de KPIs
se quedaba corta. La solución: los gráficos secundarios salen de esa
columna y arman su propia fila, DEBAJO de la grilla de 2 columnas
KPIs/principal, usando el ancho COMPLETO de la pantalla
(`grid-template-columns: repeat(auto-fit, minmax(320px, 1fr))`, así se
acomodan solos en 2, 3 o más columnas según cuántos gráficos haya y
cuánto ancho sobre, sin necesidad de un número fijo). Como ahora la
columna de KPIs solo compite en altura con UN gráfico (el principal, no
toda la pila), el desnivel que dejaba el hueco es mucho menor.

Se sacó también la regla de mobile que forzaba `.grilla` a una sola
columna: con `auto-fit` y un mínimo de 320px por tarjeta, en una pantalla
de celular esa regla ya no hacía falta (menos de 320px×2 no entran dos
columnas de todos modos) y en tablets medianos ahora se aprovecha mejor
el ancho completo (2 columnas en vez de forzar 1). Verificado que en
mobile los gráficos siguen apilados en una sola columna, sin cambios de
comportamiento ahí — tal como pidió Sd para esta ronda.

Sin cambios de backend, sin tests nuevos: es reordenar JSX existente y
ajustar CSS, sin lógica nueva que valga la pena testear aparte (mismo
criterio que el resto de esta pantalla). Verificado en Docker contra la
demo real, en desktop (los 3 gráficos secundarios pasan de una grilla de
2 confinada a 3 a todo el ancho) y en mobile (una sola columna, sin
cambios). El click-to-filter de los gráficos y el arrastre para
reordenar siguen andando igual que antes del cambio de layout.

## 2026-09-13 — Filtrado asociativo completo: gráficos en gris (v0.29.01)

Con la fase 3 y la fase 4 ya aceptadas, tocaba definir qué seguía. Se le
presentaron a Sd los cinco pendientes que quedaban de la "Fase 4 —
Profundidad" de la especificación original (`docs/especificacion-v1.md`
§9): filtrado asociativo completo, texto estructurado con parser de
Claude, reporte de calidad de datos, resubida con detección de cambios, y
almacén S3/R2 + deploy en Render. Sd contestó "están todos ok, hagámoslo
en el orden que consideres mejor" y de paso adelantó un tema pendiente:
"esquemas de actualización de datos, ej. reemplazo total cada vez,
esquema de novedades, etc." — ligado directamente al punto de resubida.

Antes de tocar nada se armó y confirmó un orden (asociativo → resubida →
calidad de datos → texto estructurado → S3/deploy) con la razón de cada
posición: el asociativo primero porque ya estaba empezado (solo faltaban
los gráficos); calidad de datos se apoya en el perfilado que ya existe;
texto estructurado es lo más exploratorio, mejor con el resto asentado;
S3/deploy al final porque necesita cuentas y credenciales de Sd y no
bloquea nada de lo anterior. Sobre esquemas de actualización se
adelantó una primera postura: empezar por "reemplazo total + reporte de
diff" (lo mínimo que ya estaba anotado como pendiente desde el paso 3) en
vez de saltar directo a un esquema incremental/de novedades, que es un
cambio de arquitectura mucho más grande (necesita una clave declarada por
fuente, decidir qué significa que una fila "no venga" en una subida
nueva, y el almacén deja de ser "un Parquet por fuente"). Sd confirmó
todo con "ok de acuerdo avanza".

También en este intercambio se aclaró explícitamente algo del entorno:
el sistema había activado "ultracode" (orquestación de varios agentes en
paralelo vía la herramienta Workflow), pero se decidió NO usarlo para
este proyecto — todo corre contra el mismo Postgres, el mismo Docker y
el mismo repo git, con reglas estrictas de no correr dos `pytest` a la
vez contra `uboard_test` y no dejar la demo alterada; paralelizar
agentes ahí generaría carreras, no velocidad real. Se avisó a Sd y se
siguió trabajando solo, como todo el resto de la sesión.

Para el primer punto (filtrado asociativo completo), antes de escribir
código se leyó el código actual (`Grafico.tsx`, `paneles.py`,
`opciones.ts`) y se consultó el skill `dataviz` — encontró justo el
patrón que hacía falta, **"emphasis"**: un valor en el acento de siempre,
el resto en gris de-emphasis. Con eso resuelto, se presentaron tres
decisiones concretas: (1) alcance = los mismos gráficos que ya son
clickeables por el paso A (barras/torta cuya dimensión coincide con un
filtro de lista existente); (2) tratamiento visual = mostrar el universo
completo del campo, no solo lo que hoy tiene datos, grisando lo que
diera cero bajo los otros filtros; (3) los gráficos con `top` (ej. "Top
vendedores") quedan afuera, porque mezclar "el ranking de los mejores N"
con "el universo completo" contradice el propio sentido del ranking. Sd
contestó "sí, dejalo así" a las tres.

La implementación no tocó `consultas/compilador.py` (sigue siendo el
único lugar que escribe SQL): `GET /dashboard/graficos/{id}` sigue
pidiendo la consulta normal del gráfico (con TODOS los filtros activos,
sin cambios ahí) y, solo cuando corresponde, pide ADEMÁS el universo
completo del campo con `consulta_opciones_lista` — la misma función que
ya existía para las opciones de un filtro — y completa `filas` con lo
que falte, marcado `disponible=False` y valor `None`. Dos guardas,
calcadas de las que ya tenía `disponibles` en las opciones de filtro
(paso 26): si la propia dimensión del gráfico ya está filtrada, no se
grisa nada (la persona ya eligió a mano qué categorías quiere ver); si no
hay NINGÚN otro filtro activo, tampoco se hace la consulta extra (no hay
nada que pudiera haber dejado algo en cero). `GraficoSalida.filas` pasó
de `[valor, métrica]` a `[valor, métrica, disponible]` — aditivo, nada
del frontend que ya existía se rompió (solo leía las dos primeras
posiciones).

Del lado del frontend, la parte más interesante fue pensar cómo se ve
honestamente un "cero grisado" en cada tipo de gráfico. En barras, la
categoría se manda como un objeto `{value: 0, itemStyle: {color:
--mudo}, label: {show: false}}` en vez de un número: sigue ocupando su
lugar en el eje, con su nombre, pero sin barra visible ni etiqueta de
valor, y se armó un tooltip a medida (reemplazando el `valueFormatter`
genérico) que le avisa "Sin datos con los filtros activos" en vez de
mostrar un `$0` engañoso. En torta se decidió NO inventar nada especial:
una porción de valor cero es 0° de arco, invisible sea cual sea el color
que se le ponga — pero el nombre igual queda listado en la leyenda
(gris), que ya es la señal honesta de "esto existe, pero no tiene datos
acá".

Verificado en Docker contra la demo real, todo con pedidos de lectura
(nada que limpiar después): un rango de fecha sin ningún dato dejó las 6
categorías de "Ventas por categoría" en gris, con sus 6 nombres
igualmente visibles en el eje; filtrando por un vendedor puntual en una
ventana de 3 días concretos apareció un caso mixto real — 5 categorías
con barra violeta y su valor, "Bebidas" sin barra ni valor, exactamente
la mezcla esperada; confirmado que filtrar por la propia dimensión del
gráfico (ej. Categoría) no agrega ningún gris; confirmado que "Top
vendedores" (con `top=10`) nunca agrega grises aunque el resto de las
condiciones se cumplan.

4 tests nuevos de API (`test_grafico_grisa_categorias_sin_datos_bajo_
otros_filtros`, `test_grafico_no_grisa_si_su_propio_filtro_esta_activo`,
`test_grafico_con_top_no_se_grisa`, `test_grafico_sin_otros_filtros_no_
grisa` — 365 en total). Sin tests nuevos de frontend, mismo criterio de
siempre.

## 2026-09-13 — Resubida con detección de cambios (v0.30.01)

Segundo pendiente de la "Fase 4 — Profundidad" original. Sd ya había
contestado la pregunta clave de la sesión anterior: "por ahora vamos con
total más diff. Luego quiero tener opciones para las dos alternativas,
UBoard pretende ser una herramienta versátil de propósito general lo más
amplia y adaptable posible". Dos decisiones en una frase: (1) arrancar
por la opción chica (reemplazo total, como siempre, más un reporte de lo
que cambió) y (2) dejar anotado que el esquema incremental/de novedades
no está descartado — solo pospuesto, porque la ambición del proyecto es
ser adaptable a distintos flujos de trabajo, no imponer uno solo. Queda
registrado acá para cuando se retome: es un cambio de arquitectura
bastante más grande (una clave declarada por fuente, decidir qué
significa que una fila "no venga" en una subida nueva, el almacén deja de
ser "un Parquet por fuente" nomás).

El "diff de esquema" ya estaba anotado como pendiente desde el paso 3,
literalmente en el comentario de `calcular_huella`: "base de la deteccion
de cambios de esquema de la fase 4". Tocaba construirlo.

La pieza central es `calcular_diff_esquema` en `app/ingesta/procesador.py`,
una función pura que compara el esquema de ANTES de una resubida contra
el de DESPUÉS: qué columnas aparecieron, cuáles desaparecieron, cuáles
cambiaron de tipo, y cuánto cambió la cantidad de filas. La parte que
vale la pena destacar es `columnas_perdidas_en_uso`: de todas las
columnas que desaparecieron, cuáles el MODELO SEMÁNTICO actual todavía
usa (`Campo.columna_origen` de la entidad ligada a esa fuente). Esto
importa porque hoy, si resubís un archivo y se te cae una columna que tu
modelo ya usa, el modelo persistido queda roto EN SILENCIO — nadie se
entera hasta que alguien intenta abrir el dashboard o guardar una versión
nueva del modelo y el compilador tira un error de columna inexistente.
El diff avisa eso en el momento, en vez de dejarlo para que explote
después en otro lugar.

Para calcular esto hizo falta que `app/ingesta` (que hasta ahora no sabía
nada de `app/modelo`) consulte el modelo semántico actual del workspace
al registrar las fuentes. Se verificó primero que no hubiera riesgo de
import circular (ni `app.modelo` ni lo que importa dependen de
`app.ingesta`) antes de agregar la dependencia.

Un detalle de implementación que valía la pena hacer bien:
`registrar_fuentes` necesitaba el esquema y la cantidad de filas VIEJOS
de la fuente ANTES de sobreescribirlos con los nuevos — el diff se
calcula en el momento exacto donde el código ya sabe "esto es una
resubida" (`fuente is not None`) pero todavía no tocó ninguno de los
campos de la fila.

El resultado de la tarea `ingesta.procesar_archivo` ahora lleva
`diff_esquema` por cada fuente reemplazada (nunca en un alta: no hay
nada contra qué comparar). Del lado del frontend, `Fuentes.tsx` muestra,
debajo del resumen de siempre ("nombre_tabla: N filas (reemplazada)"),
una línea en gris con el mismo lenguaje visual que ya usa el historial de
versiones de modelo y dashboard desde el paso 17 (`+col1, col2` para lo
nuevo, `−col1` para lo perdido, `~col1 (tipo1→tipo2)` para lo que cambió
de tipo — `compartido/diff.ts` ganó `resumirDiffEsquema`, hermana de la
`resumirDiff` que ya existía) y, si corresponde, una segunda línea
aparte en rojo y negrita avisando qué columna en uso se perdió.

Probado en Docker con una organización descartable, subiendo archivos de
verdad a través del formulario del navegador (construyendo objetos
`File` en memoria vía `DataTransfer` y disparando el evento `change` del
`<input type="file">`, no solo llamando a la API directo, para ejercitar
el camino real de subida). Se armó la secuencia completa: subir
"ventas1.csv" con una columna "Importe", cargar un modelo mínimo que la
usa, resubir sin esa columna — apareció el resumen correcto en gris
("+sucursal · −importe · +1 filas") y, en rojo, "Tu modelo usa importe,
que ya no está en el archivo nuevo." Por separado, se confirmó también el
caso sin advertencia (una resubida que agrega y saca columnas que nadie
usa) y el caso sin diff en absoluto (una fuente nueva).

7 tests nuevos de backend (372 en total): 5 puros para
`calcular_diff_esquema` en `test_ingesta_archivos.py` (columnas nuevas y
perdidas, tipo cambiado, marca solo lo que el modelo usa, delta de filas,
sin cambios) y 2 de API en `test_fuentes_api.py` (el caso de alta sin
diff, y el caso completo de aviso con un modelo real cargado). 5 tests
nuevos de vitest para `resumirDiffEsquema` (40 en total). Organización de
prueba borrada al terminar.
