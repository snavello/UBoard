"""Base declarativa comun a todas las tablas del catalogo.

Convencion de nombres de restricciones fija: asi Alembic genera migraciones
reversibles con nombres predecibles (sin ella, los indices y FKs quedan
anonimos y no se pueden borrar en un downgrade).
"""
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

CONVENCION_NOMBRES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCION_NOMBRES)
