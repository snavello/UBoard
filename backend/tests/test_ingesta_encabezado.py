"""Encoding, separador, fila de encabezado y nombres de columna. Puro."""
import pytest

from app.ingesta.codificacion import decodificar
from app.ingesta.encabezado import (
    detectar_delimitador,
    detectar_fila_encabezado,
    dividir,
    nombres_de_columnas,
    nombres_unicos,
    normalizar_nombre_columna,
)


@pytest.mark.parametrize(
    "lineas, esperado",
    [
        (["a,b,c", "1,2,3", "4,5,6"], ","),
        # Las comas decimales no confunden: el ; parte todas las lineas igual
        (["id;nombre;precio", "1;Aceite;3,10", "2;Yerba;1.250,50"], ";"),
        (["a\tb\tc", "1\t2\t3"], "\t"),
        (["a|b", "1|2", "3|4"], "|"),
        (["solo_una_columna", "1", "2"], ","),
        # Titulos arriba con comas no ganan: la mayoria de las lineas manda
        (["Listado, exportado hoy", "id;monto", "1;10", "2;20", "3;30"], ";"),
    ],
)
def test_detectar_delimitador(lineas, esperado):
    assert detectar_delimitador(lineas) == esperado


def test_dividir_respeta_comillas():
    assert dividir('1;"Aceite; 1,5L";3', ";") == ["1", "Aceite; 1,5L", "3"]
    assert dividir('a,"b ""c""",d', ",") == ["a", 'b "c"', "d"]


def test_fila_encabezado_saltea_titulos():
    filas = [
        ["Listado de pagos - Sistema Caja v3"],
        ["Exportado: 01/09/2026 10:32"],
        ["id_pago", "id_venta", "monto"],
        ["1", "10", "1.250,50"],
        ["2", "11", "300,00"],
        ["3", "", "20,00"],
    ]
    assert detectar_fila_encabezado(filas) == (2, True)


def test_fila_encabezado_con_lineas_vacias_al_inicio():
    assert detectar_fila_encabezado([[""], [], ["a", "b"], ["1", "2"]]) == (2, True)


def test_sin_encabezado_cuando_la_primera_fila_es_de_datos():
    assert detectar_fila_encabezado([["1", "2", "3"], ["4", "5", "6"]]) == (0, False)


def test_encabezado_con_nombres_repetidos_no_cuenta_como_encabezado():
    assert detectar_fila_encabezado([["x", "x"], ["1", "2"]]) == (0, False)


def test_sin_datos():
    assert detectar_fila_encabezado([]) == (None, False)
    assert detectar_fila_encabezado([[""], [None, ""]]) == (None, False)


@pytest.mark.parametrize(
    "nombre, esperado",
    [
        ("IdVenta", "id_venta"),
        ("Precio Unitario", "precio_unitario"),
        ("Año", "anio"),
        ("Descripción del Ítem", "descripcion_del_item"),
        ("ID", "id"),
        ("idProductoVendido", "id_producto_vendido"),
        ("Total$", "total"),
        ("2024 total", "c_2024_total"),
        ("  fecha_pago  ", "fecha_pago"),
        ("Ñandú", "niandu"),
        ("x" * 100, "x" * 60),
    ],
)
def test_normalizar_nombre_columna(nombre, esperado):
    assert normalizar_nombre_columna(nombre, 0) == esperado


def test_nombre_vacio_usa_la_posicion():
    assert normalizar_nombre_columna("", 2) == "columna_3"
    assert normalizar_nombre_columna(None, 0) == "columna_1"
    assert normalizar_nombre_columna("###", 4) == "columna_5"


def test_nombres_unicos_y_de_columnas():
    assert nombres_unicos(["a", "a", "b", "a"]) == ["a", "a_2", "b", "a_3"]
    assert nombres_unicos(["a", "a_2", "a"]) == ["a", "a_2", "a_3"]
    assert nombres_de_columnas(["Id", None, "Id"]) == ["id", "columna_2", "id_2"]


def test_decodificar_utf8_bom_latin1_y_utf16():
    assert decodificar("hola ñ".encode("utf-8")) == ("hola ñ", "utf-8")
    texto, encoding = decodificar("﻿id,nombre\n1,Ñandú\n".encode("utf-8"))
    assert texto.startswith("id,nombre") and encoding == "utf-8-sig"
    texto, encoding = decodificar("id;nombre\n1;Dulce de Leche Ñandú\n2;Aceite Cañuelas\n3;Jamón cocido\n".encode("latin-1"))
    assert "Ñandú" in texto and "Cañuelas" in texto and "Jamón" in texto
    assert encoding == "cp1252"
    texto, encoding = decodificar("id,nombre\n1,Ñandú\n".encode("utf-16"))
    assert "Ñandú" in texto and encoding == "utf-16"
