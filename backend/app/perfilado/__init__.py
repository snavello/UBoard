"""Perfilado: estadisticas por columna y por tabla de una fuente ingestada.

Se calcula al final de la ingesta, sobre el Parquet ya tipado, y queda
guardado en `fuente.perfil`. Es la materia prima de las heuristicas de la
fase 2 (claves, relaciones, tipos semanticos) y de lo que se le manda a Claude
en lugar de los datos crudos.
"""
from app.perfilado.perfil import PerfilColumna, PerfilFuente, TopValor, perfilar

__all__ = ["PerfilColumna", "PerfilFuente", "TopValor", "perfilar"]
