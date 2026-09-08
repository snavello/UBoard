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
