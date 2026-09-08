"""Filtros activos del dashboard -> filtros de consulta.

El frontend manda `?filtros=<JSON>` con {id_filtro: valor}:
- rango_fecha: ["2026-01-01", "2026-03-31"] (cualquier extremo puede ser null)
- lista: ["Norte", "Oeste"] (vacia = sin filtrar)
"""
import json
from typing import Any

from app.consultas.esquema import FiltroConsulta
from app.dashboard.esquema import SpecDashboard
from app.nucleo.errores import ErrorApp


def parsear_filtros_activos(crudo: str | None) -> dict[str, Any]:
    if not crudo:
        return {}
    try:
        activos = json.loads(crudo)
    except json.JSONDecodeError as error:
        raise ErrorApp("E-CONS-06", f"filtros no es JSON: {error.msg}") from None
    if not isinstance(activos, dict):
        raise ErrorApp("E-CONS-06", "filtros tiene que ser un objeto {id_filtro: valor}")
    return activos


def a_filtros_de_consulta(spec: SpecDashboard, activos: dict[str, Any]) -> list[FiltroConsulta]:
    filtros = []
    for filtro_id, valor in activos.items():
        definicion = spec.filtro(filtro_id)
        if definicion is None:
            raise ErrorApp("E-SPEC-04", f"filtro: {filtro_id!r}")
        if valor is None:
            continue
        if definicion.tipo == "rango_fecha":
            if not isinstance(valor, list) or len(valor) != 2:
                raise ErrorApp("E-CONS-06", f"{filtro_id}: un rango de fecha es [desde, hasta]")
            if all(extremo is None for extremo in valor):
                continue
            filtros.append(FiltroConsulta(campo=definicion.campo, operador="entre", valor=valor))
        else:
            if not isinstance(valor, list):
                raise ErrorApp("E-CONS-06", f"{filtro_id}: una lista de valores")
            if not valor:
                continue
            filtros.append(FiltroConsulta(campo=definicion.campo, operador="en", valor=valor))
    return filtros
