"""Tablas del catalogo. Importar este modulo registra todas en Base.metadata,
que es lo que Alembic compara para autogenerar migraciones.

Paso 1 de la fase 1: organizacion, workspace, usuario, fuente, version_modelo,
version_spec, tarea. Todavia vacio (paso 0: esqueleto).
"""
from app.catalogo.base import Base  # noqa: F401
