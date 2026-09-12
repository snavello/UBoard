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
