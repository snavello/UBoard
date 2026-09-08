# UBoard — Fase 1: lectura, dudas, decisiones técnicas, plan y skills

Fecha: 2026-09-08. Estado: para aprobación de Sd antes de escribir código.
Fuente: `docs/especificacion-v1.md` (AutoBI v1, nombre definitivo UBoard).

## (1) Lectura de la fase 1

Objetivo: que el modelo semántico y el spec de dashboard se sostengan solos, sin IA.
Con archivos reales, un modelo escrito a mano y un spec escrito a mano, el dashboard
funciona completo y los filtros afectan a todo.

Entra en la fase 1:
1. Catálogo en Postgres: organizacion, usuario (rol constructor|visualizador),
   workspace, fuente (huella nombre + esquema), version_modelo, version_spec, tarea.
   Alembic desde el primer commit.
2. Auth propia y roles. Login/logout/sesión, dependencia `exigir_rol`. El
   visualizador no tiene rutas de escritura.
3. Interfaces `AlmacenArchivos` (AlmacenLocal) y `encolar_tarea` (cola local + tabla tarea).
4. Ingesta CSV/Excel: encoding, separador, encabezados corridos, hojas múltiples ->
   Parquet en el almacén -> vista registrada en DuckDB. Huella de esquema guardada.
5. Modelo semántico: esquemas Pydantic del §4 completos (entidades, campos, relaciones,
   métricas, dimensiones de tiempo, estados, confianza), validación (referencias,
   PK consistentes, ciclos), versionado. Se carga entero desde JSON a mano.
6. Compilador consulta semántica -> SQL DuckDB (§7): entidades -> camino de joins por
   BFS -> SQL parametrizado -> tabla tipada. Único punto que genera SQL. Tests exhaustivos.
7. SpecDashboard (§5) validado contra el modelo: filtros (rango_fecha, lista), KPIs,
   gráficos (linea, barras, torta), explorador con pestañas. JSON a mano.
8. API del dashboard: opciones de filtros, KPIs, datos por gráfico, explorador
   paginado. Todo pasa por el compilador con los filtros activos.
9. Frontend React: login, constructor mínimo (subir archivos, cargar modelo y spec),
   dashboard genérico que renderiza el spec sin saber de negocio.
10. Docker Compose app + postgres, imagen multi-stage.
11. Tests pytest: ingesta y compilador desde el inicio; también auth, aislamiento y API.
12. CLAUDE.md y docs.

No entra (fases 2 a 4): perfilado, heurísticas de claves y relaciones, Claude, wizard,
chat, operaciones granulares con historial y deshacer, filtrado asociativo, resubida
con diff de esquema, texto estructurado, S3/R2, deploy en Render.

Aceptación (§9): con los 5 CSV y modelo a mano -> KPIs, 3 gráficos, explorador con
pestañas, y los filtros afectan a todo. Se agrega: el visualizador ve y filtra pero no
sube ni carga; ningún dato cruza organizaciones; `docker compose up` levanta todo.

## (2) Dudas y ambigüedades (con propuesta)

Entorno y proyecto
1. Carpeta: no hay carpeta ni repo GitHub "UBoard". Propuesta: `C:\MiTrabajoC\UBoard`.
2. Nube: repo GitHub privado `snavello/UBoard`, creado por Sd vacío; Claude configura
   el remoto y pushea. Render queda para la fase 4.
3. Node.js no está instalado. Propuesta: Node 24 LTS con `winget install OpenJS.NodeJS.LTS`.
4. Puerto Postgres 5433 para convivir con el 5432 de Mi Trabajo. Docker Desktop
   tiene que estar levantado.
5. Nombre: UBoard en todo (paquete `uboard`); AutoBI solo como referencia histórica.
6. Python 3.12.8 fijado con `.python-version`, venv + pip, requirements pinneados.

Alcance funcional
7. Workspace vs organización: tabla `workspace` que pertenece a una organización; en
   v1 una sola por organización, rutas con `/workspaces/{id}/`.
8. Operaciones sobre el modelo: en fase 1 solo cargar JSON completo + validar + nueva
   versión; `version_modelo` ya con columnas `operacion` y `diff`.
9. UI de constructor mínima además del script `cargar_prueba.py`.
10. Auth: JWT (PyJWT HS256) en cookie httpOnly `sesion_uboard`, renovación deslizante,
    15 min de inactividad, claves PBKDF2 stdlib. Confirmar duración.
11. Alta de organizaciones por script `crear_organizacion.py` (org + workspace +
    constructor + visualizador). Sin registro ni admin de plataforma en v1.
12. Excel se implementa igual, probado con Excel sintéticos en tests.
13. Expresiones de métrica: agregación simple (suma, conteo, conteo_distinto,
    promedio, minimo, maximo) y `cociente` entre dos métricas (ticket_promedio).
14. Columnas del explorador: `campo` propio o `entidad.campo` relacionado.
15. Filtros de fase 1: `rango_fecha` y `lista`. Opciones de lista = distintos sin filtrar.
16. Granularidades: dia, semana, mes, trimestre, anio.
17. Formatos: moneda | entero | decimal | porcentaje; locale es-AR; fechas dd/mm/aaaa.
18. Progreso de tareas por polling en fase 1; SSE en fase 2.
19. Voz de la UI rioplatense en segunda persona.
20. Diseño: sin marca conocida, paleta propia validada con el skill dataviz; 2-3
    propuestas de layout antes de codear el dashboard.
21. Datos de prueba: faltan; van en `datos_prueba/` antes del paso 3.
22. Versionado: `version.py`, una sola VERSION desde 0.1.01, misma regla que FLUJO.md.

## (3) Decisiones técnicas propuestas

Backend (Python 3.12)
- FastAPI 0.141 + uvicorn 0.52; Pydantic 2.13 + pydantic-settings para la config.
- SQLAlchemy 2.0.52 estilo 2.0 (`Mapped[]`, sin SQLModel), Alembic 1.19, psycopg 3.
- DuckDB 1.5.5. Las fuentes se registran como VISTAS sobre los Parquet, no se copian a
  tablas. Conexión DuckDB en memoria por workspace, reconstruida desde el catálogo.
  Resubir = reemplazar un Parquet; sin archivo .duckdb que bloquear; en fase 4 las
  vistas apuntan a s3:// con httpfs sin tocar el compilador.
- Ingesta con el propio DuckDB (`sniff_csv`/`read_csv`, `COPY ... TO parquet`),
  charset-normalizer para encoding, heurística propia para encabezados corridos,
  Excel con openpyxl (solo lectura) -> pyarrow -> Parquet, una fuente por hoja. Sin pandas.
- Auth: PyJWT + PBKDF2 stdlib. Cookie httpOnly, SameSite=Lax. Mismo origen en producción.
- AlmacenArchivos: guardar, abrir, existe, eliminar, listar, uri_para_duckdb.
  AlmacenLocal en `datos/almacen/` (gitignored, volumen en Docker).
  Rutas `org_{id}/ws_{id}/fuentes/{fuente_id}.parquet`.
- encolar_tarea(nombre, parametros) -> id. ColaLocal con ThreadPoolExecutor de 1 hilo
  y tabla tarea (estado, progreso, error, resultado).
- errores.py con códigos propios (E-INGESTA-01...) y handler global.
- Tests: pytest 9 + httpx. Ingesta y compilador puros (DuckDB en memoria). API contra
  base `uboard_test` en el mismo Postgres de Docker, transacción por test. Sin SQLite.
  Tests por archivo como en Mi Trabajo.
- Estructura del §3 más `backend/app/catalogo/`, `backend/scripts/` y `datos_prueba/`.

Frontend
- Node 24 LTS, Vite 8, React 19, TypeScript 7 (o 5.9 si un plugin no está listo),
  react-router 8, TanStack Query 5, ECharts 6 directo con hook `useGrafico`, vitest.
- CSS propio con variables + CSS Modules, sin Tailwind ni librería de componentes.
- Tema ECharts derivado de la paleta validada con validate_palette.js (claro y oscuro).
- Dev: Vite 5173 con proxy /api -> 8000. Producción: build en `backend/app/estatico/`
  servido por FastAPI con fallback a index.html.

Docker y repo
- Dockerfile multi-stage (node:24-alpine build -> python:3.12-slim); entrypoint corre
  `alembic upgrade head`.
- docker-compose.yml: postgres:16 (5433 host) + app (8000), volúmenes uboard-postgres
  y uboard-almacen. Desarrollo diario: solo Postgres en Docker, uvicorn y Vite locales.
- Rama `main` de integración, ramas `feature/...`. `.claude/launch.json` con backend y
  frontend. `.claude/skills/` con frontend-design copiado y diseno-uboard nuevo.

## (4) Plan de trabajo

Cada paso cierra con tests en verde, CLAUDE.md actualizado, commit y resumen
(hecho / falta / necesito).

| Paso | Qué | Verificación |
|---|---|---|
| 0. Entorno y esqueleto | Carpeta, git + remoto, Node, estructura, venv + requirements, Vite, Compose (5433), Alembic vacío, .env.example, CLAUDE.md, README, spec en docs/ | compose levanta; /api/salud responde; build de Vite servido por FastAPI; pytest corre |
| 1. Catálogo y auth | Tablas + migración, login/logout/yo, roles, crear_organizacion.py, errores.py | Tests de login, cookie, vencimiento, visualizador rechazado, aislamiento |
| 2. Almacén y tareas | AlmacenArchivos + AlmacenLocal, encolar_tarea + ColaLocal + tabla tarea + endpoint estado | Tests con almacén temporal y tarea de prueba |
| 3. Ingesta | CSV/Excel -> Parquet -> vista DuckDB; endpoints subir/listar/previsualizar; huella | Tests con archivos sucios sintéticos + los 5 CSV reales. Necesita los CSV |
| 4. Modelo semántico | Esquemas §4, validación, versionado, endpoints; datos_prueba/modelo.json | Tests de validación |
| 5. Compilador -> SQL | Grafo, BFS de joins, agregaciones, cociente, granularidad, filtros, orden, límite, ejecución | Tests exhaustivos de SQL y de resultados; errores por ambigüedad y ciclo |
| 6. Spec y API dashboard | Esquemas §5, endpoints filtros/kpis/grafico/explorador; datos_prueba/spec.json | Tests de API: los filtros cambian KPIs, gráficos y explorador |
| 7. Frontend | Mini sistema de diseño, propuestas de layout, login, constructor mínimo, dashboard genérico | Recorrida en navegador con capturas; contraste; modo oscuro |
| 8. Integración y cierre | Build Docker completo, cargar_prueba.py de punta a punta, checklist, docs, push | Aceptación de fase 1 con Sd |

## (5) Skills relevantes

- dataviz (Anthropic, incluido): forma según el trabajo del dato, color por función,
  validador de paleta (validate_palette.js), especificaciones de marcas, interacción,
  anti-patrones. Se aplica en el paso 7 al tema ECharts, KPIs y filtros.
- design (Claude Design): propuestas de layout editables antes de codear (paso 7).
- artifact-design / artifact-diagramming: diagrama de arquitectura y mockups compartibles.
- frontend-design (ya en Mi Trabajo): dirección visual general; se copia a UBoard.
- diseno-mi-trabajo: no reutilizable, pero su estructura es la plantilla de diseno-uboard.
- run: levantar la app y sacar capturas para verificar de verdad.
- code-review / security-review / simplify: al cierre de cada paso.
- xlsx: generar Excel sintéticos de prueba.
- Catálogo de claude.ai: sin skills específicos de dashboard, BI o ECharts.

## Qué se necesita de Sd para arrancar
1. Respuestas a las 22 dudas.
2. Carpeta y repo GitHub vacío.
3. Autorización para instalar Node y Docker Desktop levantado.
4. Los 5 CSV antes del paso 3.
