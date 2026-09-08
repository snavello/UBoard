# Imagen unica del servicio app: el frontend se compila en una etapa de Node y
# el resultado se copia a la etapa de Python, que es la que corre.

# ---- Etapa 1: build del frontend --------------------------------------------
FROM node:24-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# vite.config.ts escribe en ../backend/app/estatico => /backend/app/estatico
RUN npm run build

# ---- Etapa 2: backend ---------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /backend/app/estatico ./app/estatico
COPY docker/entrypoint.sh /entrypoint.sh
# El repo se edita en Windows: normalizar finales de linea por si llego con CRLF
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
