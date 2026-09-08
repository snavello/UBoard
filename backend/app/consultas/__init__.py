"""Consultas sobre los datos.

- motor.py: una base DuckDB en memoria por workspace con una vista por fuente.
- esquema.py: ConsultaSemantica (metricas, dimensiones, filtros, orden, limite).
- compilador.py: ConsultaSemantica + ModeloSemantico -> SQL parametrizado. El
  UNICO lugar que genera SQL.
- ejecutor.py: corre el SQL en el motor y devuelve una tabla tipada.
"""
from app.consultas.compilador import Compilador, SQLCompilado, compilar
from app.consultas.ejecutor import ResultadoConsulta, consultar, ejecutar_compilada
from app.consultas.esquema import ConsultaSemantica, DimensionConsulta, FiltroConsulta, OrdenConsulta, parsear_consulta

__all__ = [
    "Compilador",
    "ConsultaSemantica",
    "DimensionConsulta",
    "FiltroConsulta",
    "OrdenConsulta",
    "ResultadoConsulta",
    "SQLCompilado",
    "compilar",
    "consultar",
    "ejecutar_compilada",
    "parsear_consulta",
]
