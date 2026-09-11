"""Operaciones granulares sobre el spec del dashboard (puras, sin base):
cada una aplica sobre una copia, y las que no corresponden fallan con
E-SPEC-08. Se prueban sobre el spec escrito a mano para los 5 CSV."""
import json
from pathlib import Path

import pytest

from app.dashboard.edicion import OPERACIONES, aplicar_operacion, parsear_operacion
from app.dashboard.esquema import SpecDashboard
from app.dashboard.validacion import validar_spec
from app.modelo.esquema import ModeloSemantico
from app.modelo.validacion import modelo_efectivo
from app.nucleo.errores import ErrorApp

DATOS_PRUEBA = Path(__file__).resolve().parents[1].parent / "datos_prueba"


@pytest.fixture
def modelo() -> ModeloSemantico:
    contenido = json.loads((DATOS_PRUEBA / "modelo.json").read_text(encoding="utf-8"))
    return modelo_efectivo(ModeloSemantico.model_validate(contenido))


@pytest.fixture
def spec() -> SpecDashboard:
    return SpecDashboard.model_validate(json.loads((DATOS_PRUEBA / "spec.json").read_text(encoding="utf-8")))


def aplicar(spec: SpecDashboard, **operacion) -> tuple[SpecDashboard, str]:
    return aplicar_operacion(spec, parsear_operacion(operacion))


def test_lista_de_operaciones_y_parseo():
    assert "crear_grafico" in OPERACIONES and "reordenar_kpis" in OPERACIONES and len(OPERACIONES) == 14
    with pytest.raises(ErrorApp) as error:
        parsear_operacion({"operacion": "hacer_magia"})
    assert error.value.codigo == "E-SPEC-07" and "operaciones" in error.value.extra
    with pytest.raises(ErrorApp) as error:
        parsear_operacion({"operacion": "crear_filtro", "campo": "ventas.fecha", "tipo": "rango_fecha", "extra": 1})
    assert error.value.codigo == "E-SPEC-07"


def test_editar_titulo(spec, modelo):
    nuevo, resumen = aplicar(spec, operacion="editar_titulo", titulo="Panel de ventas")
    assert nuevo.titulo == "Panel de ventas" and "Panel de ventas" in resumen
    assert spec.titulo != "Panel de ventas", "el original no se toca"
    assert validar_spec(nuevo, modelo) == []


def test_filtros(spec, modelo):
    nuevo, resumen = aplicar(spec, operacion="crear_filtro", campo="productos.activo", tipo="lista", etiqueta="Activo")
    creado = next(f for f in nuevo.filtros if f.campo == "productos.activo")
    assert creado.id == "f_productos_activo" and creado.etiqueta == "Activo" and "f_productos_activo" in resumen
    assert validar_spec(nuevo, modelo) == []

    nuevo, _ = aplicar(nuevo, operacion="editar_filtro", filtro="f_productos_activo", etiqueta="¿Activo?")
    assert next(f for f in nuevo.filtros if f.id == "f_productos_activo").etiqueta == "¿Activo?"

    nuevo, _ = aplicar(nuevo, operacion="eliminar_filtro", filtro="f_productos_activo")
    assert not any(f.id == "f_productos_activo" for f in nuevo.filtros)

    with pytest.raises(ErrorApp) as error:
        aplicar(spec, operacion="eliminar_filtro", filtro="nada")
    assert error.value.codigo == "E-SPEC-08"
    with pytest.raises(ErrorApp):
        aplicar(spec, operacion="crear_filtro", id="f_fecha", campo="ventas.fecha", tipo="rango_fecha")


def test_kpis_y_reordenar(spec, modelo):
    nuevo, resumen = aplicar(spec, operacion="crear_kpi", metrica="vendedores_activos", titulo="Vendedores activos")
    creado = next(k for k in nuevo.kpis if k.metrica == "vendedores_activos")
    assert creado.titulo == "Vendedores activos" and creado.id in resumen
    assert validar_spec(nuevo, modelo) == []

    nuevo, _ = aplicar(nuevo, operacion="editar_kpi", kpi=creado.id, titulo="Activos")
    assert next(k for k in nuevo.kpis if k.id == creado.id).titulo == "Activos"

    ids_originales = [k.id for k in spec.kpis]
    nuevo, resumen = aplicar(spec, operacion="reordenar_kpis", orden=[ids_originales[-1]])
    assert [k.id for k in nuevo.kpis][0] == ids_originales[-1]
    assert set(k.id for k in nuevo.kpis) == set(ids_originales), "reordenar no pierde ninguno"
    assert ids_originales[-1] in resumen

    with pytest.raises(ErrorApp):
        aplicar(spec, operacion="reordenar_kpis", orden=["no_existe"])

    nuevo, _ = aplicar(spec, operacion="eliminar_kpi", kpi=ids_originales[0])
    assert not any(k.id == ids_originales[0] for k in nuevo.kpis)
    with pytest.raises(ErrorApp):
        aplicar(spec, operacion="eliminar_kpi", kpi="no_existe")


def test_graficos(spec, modelo):
    nuevo, resumen = aplicar(
        spec, operacion="crear_grafico", tipo="barras", metrica="total_ventas", dimension="vendedores.sucursal", top=5, titulo="Ventas por sucursal"
    )
    creado = next(g for g in nuevo.graficos if g.dimension == "vendedores.sucursal")
    assert creado.tipo == "barras" and creado.titulo == "Ventas por sucursal" and creado.top == 5
    assert creado.id in resumen and "barras" in resumen
    assert validar_spec(nuevo, modelo) == []

    nuevo, _ = aplicar(nuevo, operacion="editar_grafico", grafico=creado.id, titulo="Por sucursal", top=3)
    editado = next(g for g in nuevo.graficos if g.id == creado.id)
    assert editado.titulo == "Por sucursal" and editado.top == 3 and editado.metrica == "total_ventas", "lo no enviado no cambia"

    nuevo, _ = aplicar(nuevo, operacion="eliminar_grafico", grafico=creado.id)
    assert not any(g.id == creado.id for g in nuevo.graficos)

    # Una dimension que multiplicaria filas: la operacion se aplica, pero no valida (lo detecta guardar, no esta capa)
    invalido, _ = aplicar(spec, operacion="crear_grafico", tipo="barras", metrica="total_ventas", dimension="medios_pago.nombre")
    assert any(error.codigo == "SPEC-CONSULTA" for error in validar_spec(invalido, modelo))

    with pytest.raises(ErrorApp):
        aplicar(spec, operacion="editar_grafico", grafico="no_existe", titulo="x")


def test_pestanias(spec, modelo):
    nuevo, resumen = aplicar(spec, operacion="eliminar_pestania", entidad="pagos")
    assert not any(p.entidad == "pagos" for p in nuevo.explorador.pestanias)
    assert "pagos" in resumen
    assert validar_spec(nuevo, modelo) == []

    nuevo, resumen = aplicar(nuevo, operacion="crear_pestania", entidad="pagos", titulo="Pagos", columnas=["fecha_pago", "monto"])
    creada = nuevo.pestania("pagos")
    assert creada.titulo == "Pagos" and creada.columnas == ["fecha_pago", "monto"] and creada.tamanio_pagina == 25
    assert validar_spec(nuevo, modelo) == []

    nuevo, _ = aplicar(nuevo, operacion="editar_pestania", entidad="pagos", tamanio_pagina=50, metricas=["cantidad_pagos"])
    editada = nuevo.pestania("pagos")
    assert editada.tamanio_pagina == 50 and editada.metricas == ["cantidad_pagos"] and editada.columnas == ["fecha_pago", "monto"]

    with pytest.raises(ErrorApp):
        aplicar(spec, operacion="crear_pestania", entidad="pagos", columnas=["monto"])  # ya existe
    with pytest.raises(ErrorApp):
        aplicar(spec, operacion="editar_pestania", entidad="no_existe", titulo="x")
