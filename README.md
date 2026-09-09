# UBoard

Un BI que se construye solo. Subís archivos (CSV, Excel), UBoard infiere la
estructura y las relaciones, arma un modelo semántico y te propone un
dashboard con filtros, KPIs, gráficos y explorador. Todo se ajusta por wizard
o en lenguaje natural.

Especificación: [`docs/especificacion-v1.md`](docs/especificacion-v1.md).
Contexto para Claude Code: [`CLAUDE.md`](CLAUDE.md).

## Requisitos
- Python 3.12, Node 24 LTS, Docker Desktop.

## Puesta en marcha (desarrollo)
```bash
cp .env.example .env
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
docker compose up -d postgres
cd backend && ../.venv/Scripts/python.exe -m alembic upgrade head && cd ..
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000 --app-dir backend
```
En otra terminal, el frontend con recarga en vivo:
```bash
cd frontend && npm install && npm run dev
```
Abrir http://localhost:5173. La API queda en http://localhost:8000/api/docs.

## Todo en Docker (como producción)
```bash
docker compose up --build -d
docker compose exec app python scripts/crear_organizacion.py demo
.venv/Scripts/python.exe backend/scripts/cargar_prueba.py --url http://localhost:8000
```
Abrir http://localhost:8000 e ingresar con los accesos de la demo (ver `CLAUDE.md`).
El checklist de aceptación de la fase 1 está en `docs/fase1-aceptacion.md`.

## Tests
Desde `backend/`, un archivo por vez:
```bash
for f in tests/test_*.py; do ../.venv/Scripts/python.exe -m pytest "$f" || break; done
```
