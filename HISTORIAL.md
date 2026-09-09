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
