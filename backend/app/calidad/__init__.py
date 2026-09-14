"""Reporte de calidad de datos (fase 4, "Profundidad"): al vuelo, sobre una
fuente ya ingestada, a partir del perfilado (paso 9), el esquema tipado
(paso 3) y, si hay uno cargado, el modelo semantico (claves y relaciones
confirmadas). Nada se persiste.
"""
from app.calidad.analisis import calcular_reporte
from app.calidad.esquema import ProblemaCalidad, ReporteCalidad

__all__ = ["ProblemaCalidad", "ReporteCalidad", "calcular_reporte"]
