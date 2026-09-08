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
