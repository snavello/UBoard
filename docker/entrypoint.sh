#!/bin/sh
# Aplica las migraciones pendientes y arranca el servidor. Si la migracion
# falla, el contenedor no levanta: mejor eso que una app corriendo contra un
# esquema viejo.
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
