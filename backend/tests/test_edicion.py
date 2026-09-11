"""Operaciones granulares sobre el modelo (puras, sin base): cada una aplica
sobre una copia, deja lo tocado como `usuario`, y las que no corresponden
fallan con E-MOD-05. Se prueban sobre el modelo escrito a mano y sobre uno
propuesto (todo `propuesta`)."""
import copy
import json
from pathlib import Path

import pytest

from app.modelo.edicion import OPERACIONES, aplicar_operacion, parsear_operacion
from app.modelo.esquema import ModeloSemantico
from app.modelo.validacion import modelo_efectivo, validar_estructura
from app.nucleo.errores import ErrorApp

DATOS_PRUEBA = Path(__file__).resolve().parents[1].parent / "datos_prueba"


@pytest.fixture
def modelo() -> ModeloSemantico:
    return ModeloSemantico.model_validate(json.loads((DATOS_PRUEBA / "modelo.json").read_text(encoding="utf-8")))


@pytest.fixture
def propuesto(modelo) -> ModeloSemantico:
    """El modelo a mano pero como si lo hubiera propuesto la heuristica."""
    contenido = modelo.model_dump()
    for entidad in contenido["entidades"]:
        entidad["origen"] = "heuristica"
        for campo in entidad["campos"]:
            if campo["id"] not in entidad["clave_primaria"]:
                campo.update(estado="propuesta", origen="heuristica", confianza=0.95 if campo["tipo_semantico"] != "texto_libre" else 0.7)
    for relacion in contenido["relaciones"]:
        relacion.update(estado="propuesta", confianza=0.9)
    contenido["relaciones"][0]["confianza"] = 0.6
    for metrica in contenido["metricas"]:
        metrica.update(estado="propuesta", origen="llm", confianza=0.8)
    return ModeloSemantico.model_validate(contenido)


def aplicar(modelo: ModeloSemantico, **operacion) -> tuple[ModeloSemantico, str]:
    return aplicar_operacion(modelo, parsear_operacion(operacion))


def test_lista_de_operaciones_y_parseo():
    assert "renombrar_campo" in OPERACIONES and "confirmar_todo" in OPERACIONES and len(OPERACIONES) == 21
    with pytest.raises(ErrorApp) as error:
        parsear_operacion({"operacion": "borrar_todo"})
    assert error.value.codigo == "E-MOD-04" and "operaciones" in error.value.extra
    with pytest.raises(ErrorApp) as error:
        parsear_operacion({"operacion": "renombrar_campo", "entidad": "ventas", "campo": "importe", "nombre": "", "otro": 1})
    assert error.value.codigo == "E-MOD-04"
    assert {e["ubicacion"] for e in error.value.extra["errores"]} >= {"renombrar_campo.nombre", "renombrar_campo.otro"}


def test_entidades(modelo):
    nuevo, resumen = aplicar(modelo, operacion="renombrar_entidad", entidad="ventas", nombre="Operaciones", descripcion="Cada ticket")
    assert nuevo.entidad("ventas").nombre == "Operaciones" and nuevo.entidad("ventas").descripcion == "Cada ticket"
    assert nuevo.entidad("ventas").origen == "usuario" and "Operaciones" in resumen
    assert modelo.entidad("ventas").nombre == "Ventas", "el original no se toca"

    nuevo, _ = aplicar(modelo, operacion="asignar_tipo_entidad", entidad="productos", tipo="hechos")
    assert nuevo.entidad("productos").tipo == "hechos"

    nuevo, _ = aplicar(modelo, operacion="agregar_sinonimo", entidad="ventas", sinonimo="tickets")
    nuevo, _ = aplicar(nuevo, operacion="agregar_sinonimo", entidad="ventas", sinonimo="tickets")
    assert nuevo.entidad("ventas").sinonimos.count("tickets") == 1
    nuevo, _ = aplicar(nuevo, operacion="quitar_sinonimo", entidad="ventas", sinonimo="tickets")
    assert "tickets" not in nuevo.entidad("ventas").sinonimos

    with pytest.raises(ErrorApp) as error:
        aplicar(modelo, operacion="renombrar_entidad", entidad="nada", nombre="X")
    assert error.value.codigo == "E-MOD-05"


def test_clave_primaria(propuesto):
    nuevo, _ = aplicar(propuesto, operacion="marcar_clave_primaria", entidad="productos", campos=["nombre"])
    productos = nuevo.entidad("productos")
    assert productos.clave_primaria == ["nombre"]
    assert productos.campo("nombre").estado == "confirmada" and productos.campo("nombre").tipo_semantico == "identificador"
    assert validar_estructura(nuevo) == [] or all(e.codigo != "MOD-PK-NO-CONFIRMADA" for e in validar_estructura(nuevo))
    # El id viejo sigue siendo un campo, ya no clave: ahora la relacion que apunta a productos.id_producto no valida
    assert any(e.codigo == "MOD-REL-NO-PK" for e in validar_estructura(nuevo))


def test_campos(propuesto):
    nuevo, _ = aplicar(propuesto, operacion="renombrar_campo", entidad="ventas", campo="importe", nombre="Monto facturado")
    campo = nuevo.entidad("ventas").campo("importe")
    assert campo.nombre == "Monto facturado" and campo.origen == "usuario" and campo.estado == "propuesta"

    nuevo, _ = aplicar(nuevo, operacion="asignar_tipo_semantico", entidad="vendedores", campo="email", tipo_semantico="categoria")
    assert nuevo.entidad("vendedores").campo("email").tipo_semantico == "categoria"
    assert nuevo.entidad("vendedores").campo("email").confianza == 1.0

    nuevo, _ = aplicar(nuevo, operacion="confirmar_campo", entidad="ventas", campo="importe")
    assert nuevo.entidad("ventas").campo("importe").estado == "confirmada"
    nuevo, _ = aplicar(nuevo, operacion="rechazar_campo", entidad="vendedores", campo="email")
    assert nuevo.entidad("vendedores").campo("email").estado == "rechazada"
    assert nuevo.entidad("vendedores").campo("email").origen == "usuario", "rechazar no cambia el origen"

    for operacion in ({"operacion": "rechazar_campo"}, {"operacion": "asignar_tipo_semantico", "tipo_semantico": "monto"}):
        with pytest.raises(ErrorApp) as error:
            aplicar(propuesto, entidad="ventas", campo="id_venta", **operacion)
        assert error.value.codigo == "E-MOD-05" and "clave primaria" in error.value.detalle


def test_relaciones(propuesto):
    nuevo, _ = aplicar(propuesto, operacion="confirmar_relacion", relacion="ventas_vendedor")
    relacion = next(r for r in nuevo.relaciones if r.id == "ventas_vendedor")
    assert relacion.estado == "confirmada" and relacion.confianza == 0.6, "confirmar no toca la confianza"
    assert nuevo.entidad("ventas").campo("id_vendedor").estado == "confirmada", "confirma los campos que usa"
    assert validar_estructura(nuevo) == []

    nuevo, _ = aplicar(nuevo, operacion="rechazar_relacion", relacion="pagos_medio")
    assert next(r for r in nuevo.relaciones if r.id == "pagos_medio").estado == "rechazada"
    assert len(modelo_efectivo(nuevo).relaciones) == 3

    nuevo, _ = aplicar(nuevo, operacion="eliminar_relacion", relacion="pagos_medio")
    assert not any(r.id == "pagos_medio" for r in nuevo.relaciones)

    nuevo, resumen = aplicar(
        nuevo,
        operacion="crear_relacion",
        desde={"entidad": "pagos", "campo": "id_medio_pago"},
        hacia={"entidad": "medios_pago", "campo": "id_medio_pago"},
    )
    creada = next(r for r in nuevo.relaciones if r.desde.referencia == "pagos.id_medio_pago")
    assert creada.id == "pagos_id_medio_pago" and creada.estado == "confirmada" and creada.confianza == 1.0
    assert creada.evidencia == {"origen": "usuario"} and "→" in resumen
    assert nuevo.entidad("pagos").campo("id_medio_pago").tipo_semantico == "clave_foranea"
    assert validar_estructura(nuevo) == []

    with pytest.raises(ErrorApp) as error:
        aplicar(nuevo, operacion="crear_relacion", desde={"entidad": "pagos", "campo": "id_medio_pago"}, hacia={"entidad": "medios_pago", "campo": "id_medio_pago"})
    assert error.value.codigo == "E-MOD-05" and "ya existe" in error.value.detalle
    with pytest.raises(ErrorApp):
        aplicar(nuevo, operacion="confirmar_relacion", relacion="nada")


def test_metricas(modelo):
    nuevo, _ = aplicar(
        modelo,
        operacion="crear_metrica",
        id="descuento_promedio",
        nombre="Precio promedio",
        expresion={"agregacion": "promedio", "campo": "ventas.precio_unitario"},
        formato="moneda",
    )
    metrica = nuevo.metrica("descuento_promedio")
    assert metrica.origen == "usuario" and metrica.estado == "confirmada" and metrica.formato == "moneda"
    assert validar_estructura(nuevo) == []

    nuevo, _ = aplicar(nuevo, operacion="editar_metrica", metrica="descuento_promedio", nombre="Precio medio", formato="decimal")
    assert nuevo.metrica("descuento_promedio").nombre == "Precio medio" and nuevo.metrica("descuento_promedio").formato == "decimal"
    assert nuevo.metrica("descuento_promedio").expresion.agregacion == "promedio", "lo no enviado no cambia"

    nuevo, _ = aplicar(
        nuevo, operacion="editar_metrica", metrica="descuento_promedio", expresion={"operacion": "division", "izquierda": "cantidad_ventas", "derecha": 2.0}
    )
    assert nuevo.metrica("descuento_promedio").expresion.operacion == "division"
    assert validar_estructura(nuevo) == []

    nuevo, _ = aplicar(nuevo, operacion="rechazar_metrica", metrica="cuotas_promedio")
    assert nuevo.metrica("cuotas_promedio").estado == "rechazada"
    nuevo, _ = aplicar(nuevo, operacion="confirmar_metrica", metrica="cuotas_promedio")
    assert nuevo.metrica("cuotas_promedio").estado == "confirmada"

    with pytest.raises(ErrorApp) as error:
        aplicar(nuevo, operacion="eliminar_metrica", metrica="total_ventas")
    assert "ticket_promedio" in error.value.detalle, "la usa un cociente"
    nuevo, _ = aplicar(nuevo, operacion="eliminar_metrica", metrica="ticket_promedio")

    nuevo, resumen = aplicar(
        nuevo,
        operacion="crear_metrica",
        id="margen",
        nombre="Margen",
        expresion={"operacion": "resta", "izquierda": "total_ventas", "derecha": "total_pagado"},
        formato="moneda",
    )
    assert nuevo.metrica("margen").expresion.operacion == "resta" and "margen" in resumen
    assert validar_estructura(nuevo) == []

    with pytest.raises(ErrorApp) as error:
        aplicar(nuevo, operacion="eliminar_metrica", metrica="total_ventas")
    assert "margen" in error.value.detalle, "la usa la formula"
    nuevo, _ = aplicar(nuevo, operacion="eliminar_metrica", metrica="margen")

    nuevo, _ = aplicar(nuevo, operacion="eliminar_metrica", metrica="total_ventas")
    assert nuevo.metrica("total_ventas") is None
    with pytest.raises(ErrorApp):
        aplicar(nuevo, operacion="crear_metrica", id="cantidad_ventas", nombre="X", expresion={"agregacion": "conteo", "campo": "ventas.id_venta"})


def test_dimensiones_de_tiempo(modelo):
    nuevo, _ = aplicar(modelo, operacion="agregar_dimension_tiempo", campo="vendedores.fecha_ingreso", granularidades=["anio"])
    assert any(d.campo == "vendedores.fecha_ingreso" and d.granularidades == ["anio"] for d in nuevo.dimensiones_tiempo)
    nuevo, _ = aplicar(nuevo, operacion="agregar_dimension_tiempo", campo="vendedores.fecha_ingreso", granularidades=["mes", "anio"])
    assert [d for d in nuevo.dimensiones_tiempo if d.campo == "vendedores.fecha_ingreso"][0].granularidades == ["mes", "anio"]
    nuevo, _ = aplicar(nuevo, operacion="quitar_dimension_tiempo", campo="vendedores.fecha_ingreso")
    assert not any(d.campo == "vendedores.fecha_ingreso" for d in nuevo.dimensiones_tiempo)
    with pytest.raises(ErrorApp):
        aplicar(nuevo, operacion="quitar_dimension_tiempo", campo="vendedores.fecha_ingreso")
    with pytest.raises(ErrorApp):
        aplicar(nuevo, operacion="agregar_dimension_tiempo", campo="ventas.nada")


def test_confirmar_todo_lo_verde(propuesto):
    antes = modelo_efectivo(propuesto)
    assert antes.metricas == [] and len(antes.relaciones) == 3

    nuevo, resumen = aplicar(propuesto, operacion="confirmar_todo", seccion="campos", entidad="ventas")
    ventas = nuevo.entidad("ventas")
    assert all(campo.estado == "confirmada" for campo in ventas.campos)
    assert nuevo.entidad("vendedores").campo("email").estado == "propuesta", "otra entidad no se toca"
    assert "confirmados en bloque" in resumen

    nuevo, _ = aplicar(nuevo, operacion="confirmar_todo")
    assert nuevo.entidad("vendedores").campo("email").estado == "propuesta", "0.7 < 0.9: queda amarillo"
    assert nuevo.entidad("vendedores").campo("sucursal").estado == "confirmada"
    relaciones = {r.id: r.estado for r in nuevo.relaciones}
    assert relaciones == {"ventas_vendedor": "propuesta", "ventas_producto": "confirmada", "pagos_venta": "confirmada", "pagos_medio": "confirmada"}
    assert all(m.estado == "propuesta" for m in nuevo.metricas), "0.8 < 0.9"

    nuevo, _ = aplicar(nuevo, operacion="confirmar_todo", seccion="metricas", minimo_confianza=0.8)
    assert all(m.estado == "confirmada" for m in nuevo.metricas)
    assert validar_estructura(nuevo) == []
    assert len(modelo_efectivo(nuevo).metricas) == 8
