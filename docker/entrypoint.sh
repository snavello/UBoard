#!/bin/sh
# Aplica las migraciones pendientes y arranca el servidor. Si la migracion
# falla, el contenedor no levanta: mejor eso que una app corriendo contra un
# esquema viejo.
#
# El puerto respeta $PORT si el entorno lo define (Render se lo pasa al
# contenedor; por defecto usa 10000, no el 8000 que fija este Dockerfile) y
# si no, usa 8000 como siempre en Docker Compose local.
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
